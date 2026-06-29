import asyncio
import logging
import os
import time
import uuid

import aiohttp
from tinydb import Query, TinyDB

logger = logging.getLogger(__name__)


db = TinyDB("data/db.json")
auth_table = db.table("auth")


def produce_state_str() -> str:
    return str(uuid.uuid4())


async def access_token_loop():
    """
    A async loop to refresh Todoist access token periodically.
    """
    while True:
        await asyncio.sleep(3200)
        logger.info("Refreshing access token...")
        db_all = auth_table.all()
        if len(db_all) == 0:
            logger.warning(
                "No existing refresh token available. Check whether the initial authentication has been completed"
            )
            continue
        most_recent_timestamp = max([doc["timestamp"] for doc in db_all])
        recent_refresh_token = [
            doc["refresh_token"]
            for doc in db_all
            if doc["timestamp"] == most_recent_timestamp
        ][0]
        try:
            await token_refresh(recent_refresh_token)
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


async def token_refresh(refresh_token: str):
    """
    Send token refresh request to Todoist, and insert response to db, fallable
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url="https://api.todoist.com/oauth/access_token",
            data={
                "client_id": os.environ["CLIENT_ID"],
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_secret": os.environ["CLIENT_SECRET"],
            },
        ) as resp:
            token_response = await resp.json()
    if "access_token" not in token_response:
        raise ValueError("Token refresh response invalid")
    auth_table.insert(token_response | {"timestamp": time.time()})
