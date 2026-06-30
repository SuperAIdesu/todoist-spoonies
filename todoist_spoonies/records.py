import asyncio
import logging
import os
from datetime import datetime, time
from typing import Optional

from aiohttp import ClientSession
from pydantic import BaseModel
from tinydb import Query, TinyDB
from todoist_auth import get_auth_headers

logger = logging.getLogger(__name__)


db = TinyDB("data/db.json")
tasks_table = db.table("tasks")
settings_table = db.table("settings")


class CompletedTaskRecord(BaseModel):
    """
    A completed Todoist task
    """

    id: str
    content: str
    description: str
    child_order: int
    priority: int
    project_id: str
    project_name: Optional[str]
    section_id: Optional[str]
    section_name: Optional[str]
    parent_id: Optional[str]
    labels: list[str]
    added_at: datetime
    completed_at: datetime
    spoons: Optional[int]

    def should_readd(self) -> bool:
        """
        Returns True if the task should be readded
        """
        tpl_project = os.environ["TEMPLATE_PROJECT_NAME"]
        if tpl_project == "":
            logger.warning("TEMPLATE_PROJECT_NAME not set, won't re-add tasks!")
        # NOTE: not supporting sub-tasks for now
        if self.project_name == tpl_project and self.parent_id is None:
            return True
        return False

    async def readd(self, delay=120):
        """
        Readds the task to same project&section.
        Delay 120 secs to avoid confusing user in Todoist client UI.
        """
        await asyncio.sleep(delay)
        async with ClientSession(headers=get_auth_headers()) as session:
            async with session.post(
                url="https://api.todoist.com/api/v1/tasks",
                json={
                    "content": self.content,
                    "description": self.description,
                    "project_id": self.project_id,
                    "section_id": self.section_id,
                    "order": self.child_order,
                    "labels": self.labels,
                    "priority": self.priority,
                },
            ) as resp:
                if resp.status == 200:
                    logger.info(f"Task ID {self.id} readded")
                    return
                else:
                    logger.error(resp)
                    raise ValueError("Todoist API Response invalid!")


def get_records_by_time(start: datetime, end: datetime) -> list[CompletedTaskRecord]:
    """
    Return completed task records during the time period.
    """
    q = Query()
    records = tasks_table.search(q.completed_at >= start.isoformat())
    records = [r for r in records if r["completed_at"] <= end.isoformat()]
    return [CompletedTaskRecord(**r) for r in records]


def build_today_message(records: list[CompletedTaskRecord]) -> str:
    """Build a text summary of today's completed tasks."""
    total_spoons = sum(r.spoons or 0 for r in records)
    lines = [
        "Hi there,",
        f"__Today you have used {total_spoons} spoons to complete {len(records)} tasks:__",
    ]
    for r in records:
        spoon_str = f" ({r.spoons}x🥄)" if r.spoons else ""
        lines.append(f"- {r.content}{spoon_str} in {r.project_name}->{r.section_name}")
    lines.append(
        "*If you forgot to tag the spoon label on the task, feel free to complete a placeholder task in your template project so that it could be tracked.*"
    )
    lines.append("Enjoy the rest of your day!")
    return "\n".join(lines)


class DailySummaryConfig(BaseModel):
    """
    Settings for the scheduled daily summary
    """

    enabled: bool = False
    scheduled_time: time = time(22, 30)

    @staticmethod
    def load() -> "DailySummaryConfig":
        q = Query()
        result = settings_table.search(q.key == "daily_summary")
        if result:
            return DailySummaryConfig(**result[0])
        return DailySummaryConfig()

    def save(self):
        settings_table.remove(Query().key == "daily_summary")
        settings_table.insert({"key": "daily_summary", **self.model_dump(mode="json")})
