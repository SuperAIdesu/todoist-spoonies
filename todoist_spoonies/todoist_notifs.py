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

    async def readd(self):
        """
        Readds the task to same project&section
        """
        async with ClientSession(headers=get_auth_headers()) as session:
            async with session.post(
                url="https://api.todoist.com/api/v1/tasks",
                data={
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
                    raise ValueError("Todoist API Response invalid!")


async def process_event(data: dict):
    """
    Process Todoist webhook notification
    """
    event_name = data.get("event_name")
    event_data = data.get("event_data")
    if not isinstance(event_data, dict):
        raise ValueError("Expecting a valid event_data JSON!")
    match event_name:
        case "item:completed":
            await process_completion(event_data)
        case "item:uncompleted":
            pass
        case _:
            logger.info("Todoist event type not supported or used!")


async def process_completion(event_data: dict):
    """
    Add the completed task to DB, and re-add the same task if needed.
    """
    task_record = CompletedTaskRecord(
        id=event_data["id"],
        content=event_data["content"],
        description=event_data["description"],
        child_order=event_data["child_order"],
        priority=event_data["priority"],
        project_id=event_data["project_id"],
        project_name=await get_name_from_id("projects", event_data["project_id"]),
        section_id=event_data["section_id"],
        section_name=await get_name_from_id("sections", event_data["section_id"])
        if event_data["section_id"] is not None
        else None,
        parent_id=event_data["parent_id"],
        labels=event_data["labels"],
        added_at=event_data["added_at"],
        # For recurring tasks, completed_at will be None. Use updated_at instead
        completed_at=event_data["completed_at"]
        if event_data["completed_at"] is not None
        else event_data["updated_at"],
        spoons=match_spoon_from_labels(event_data["labels"]),
    )
    tasks_table.insert(task_record.model_dump(mode="json"))
    logger.info(f"Task ID {task_record.id} inserted to DB")

    if task_record.should_readd():
        # Delay 120 secs to avoid confusing user in Todoist client UI
        await asyncio.sleep(120)
        await task_record.readd()


async def process_uncompletion(event_data: dict):
    """
    Remove the latest completed task record (by completed_at) if in DB.
    """
    task_id = event_data["id"]
    records = tasks_table.search(Query().id == task_id)
    if not records:
        logger.info(f"Task ID {task_id} not found in DB")
        return
    latest = max(records, key=lambda r: r["completed_at"])
    tasks_table.remove(doc_ids=[latest["_id"]])
    logger.info(f"Task ID {task_id} removed from DB")


async def get_name_from_id(type: str, id: str) -> str:
    """
    Call Todoist API to get project/section name.
    """
    if type not in ["projects", "sections"]:
        raise NotImplementedError("Not supported!")
    async with ClientSession(headers=get_auth_headers()) as session:
        async with session.get(
            url=f"https://api.todoist.com/api/v1/{type}/{id}",
        ) as resp:
            if resp.status == 200:
                response = await resp.json()
                return response["name"]
            else:
                raise ValueError("Todoist API Response invalid!")


def match_spoon_from_labels(labels: list[str]) -> Optional[int]:
    """
    Attempt to match spoon number from labels. If failed to match, return None.
    """
    prefix = os.environ["LABEL_PREFIX"]
    if prefix == "":
        logger.warning("LABEL_PREFIX not set, can't match from label!")
        return None
    for label in labels:
        if label.startswith(prefix):
            suffix = label[len(prefix) :]
            try:
                return int(suffix)
            except Exception:
                continue
    return None
