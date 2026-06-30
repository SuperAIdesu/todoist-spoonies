import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

from aiohttp import ClientSession
from pydantic import BaseModel
from tinydb import Query, TinyDB
from todoist_auth import get_auth_headers

logger = logging.getLogger(__name__)


db = TinyDB("data/db.json")
tasks_table = db.table("tasks")


class CompletedTaskRecord(BaseModel):
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
    pass
