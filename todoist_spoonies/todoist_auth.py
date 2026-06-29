import asyncio
import logging
import os
import time
import uuid
from typing import Optional

import aiohttp
from tinydb import Query, TinyDB

logger = logging.getLogger(__name__)


db = TinyDB("data/db.json")
auth_table = db.table("auth")


def produce_state_str() -> str:
    return str(uuid.uuid4())


def get_recent_auth_record() -> Optional[dict]:
    """
    Get the most recent entry in "auth" DB table.
    """
    db_all = auth_table.all()
    if len(db_all) == 0:
        return None
    most_recent_timestamp = max([doc["timestamp"] for doc in db_all])
    return [doc for doc in db_all if doc["timestamp"] == most_recent_timestamp][0]


def is_token_expired() -> bool:
    """
    Check if the current access token has expired.
    Returns True if expired or if required fields are missing.
    """
    record = get_recent_auth_record()
    if record is None or "expires_in" not in record:
        return True
    expiration_time = record["timestamp"] + record["expires_in"]
    return time.time() >= expiration_time


async def access_token_loop():
    """
    A async loop to refresh Todoist access token periodically.
    """
    if is_token_expired():
        logger.info("Token already expired, refreshing immediately...")
        try:
            await token_refresh()
            logger.info("Immediate token refresh success!")
        except Exception as e:
            logger.error("Immediate token refresh failed!")
            logger.error(e)

    while True:
        await asyncio.sleep(3200)
        logger.info("Refreshing access token...")
        try:
            await token_refresh()
        except Exception as e:
            logger.error("Token refresh failed!")
            logger.error(e)
            continue
        # clean old table entries
        auth_table.remove(Query().timestamp < time.time() - 18000)
        logger.info("Token refresh success!")


async def token_exchange(code: str):
    """
    Send token exchange request to Todoist, and insert response to db, fallable
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url="https://api.todoist.com/oauth/access_token",
            data={
                "client_id": os.environ["CLIENT_ID"],
                "client_secret": os.environ["CLIENT_SECRET"],
                "code": code,
            },
        ) as resp:
            token_response = await resp.json()
    if "error" in token_response:
        raise ValueError("Bad credentials")
    auth_table.insert(token_response | {"timestamp": time.time()})


async def token_refresh():
    """
    Send token refresh request to Todoist, and insert response to db, fallable
    """
    recent_record = get_recent_auth_record()
    if recent_record is None:
        raise ValueError(
            "No existing token found! Check if initial OAuth workflow has been completed."
        )
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url="https://api.todoist.com/oauth/access_token",
            data={
                "client_id": os.environ["CLIENT_ID"],
                "grant_type": "refresh_token",
                "refresh_token": recent_record["refresh_token"],
                "client_secret": os.environ["CLIENT_SECRET"],
            },
        ) as resp:
            token_response = await resp.json()
    if "access_token" not in token_response:
        raise ValueError("Token refresh response invalid")
    auth_table.insert(token_response | {"timestamp": time.time()})


def get_auth_headers() -> dict:
    """
    Build the Todoist API auth headers
    """
    auth_record = get_recent_auth_record()
    if auth_record is None or "access_token" not in auth_record:
        raise ValueError("No existing acess token found!")
    access_token = auth_record["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    return headers
