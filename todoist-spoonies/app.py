import argparse
import asyncio
import logging
import os
import time

import ids
import requests
from dotenv import load_dotenv
from robyn import Response, Robyn, status_codes
from tinydb import Query, TinyDB

logger = logging.getLogger()

load_dotenv()
STATE = ids.produce_state_str()

app = Robyn(__file__)
db = TinyDB("data/db.json")
auth_table = db.table("auth")


def oauth_messages():
    logger.info("Initializing OAuth workflow... Open the below URL:")
    logger.info(
        f"https://app.todoist.com/oauth/authorize?client_id={os.environ['CLIENT_ID']}&scope=data:read_write&state={STATE}"
    )


async def access_token_loop():
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
        token_response = requests.post(
            url="https://api.todoist.com/oauth/access_token",
            data={
                "client_id": os.environ["CLIENT_ID"],
                "grant_type": "refresh_token",
                "refresh_token": recent_refresh_token,
                "client_secret": os.environ["CLIENT_SECRET"],
            },
        ).json()
        auth_table.insert(token_response | {"timestamp": time.time()})
        # clean old table entries
        auth_table.remove(Query().timestamp < time.time() - 18000)
        logger.info("Token refresh success!")


@app.get("/")
async def h(request):
    logger.info("Received redirected authentication request")
    returned_state: str = request.query_params.get("state", "")
    if returned_state != STATE:
        return Response(
            status_code=status_codes.HTTP_400_BAD_REQUEST,
            headers={"Content-Type": "text/plain"},
            body="Invalid STATE param received",
        )
    code: str = request.query_params.get("code", "")
    token_response = requests.post(
        url="https://api.todoist.com/oauth/access_token",
        data={
            "client_id": os.environ["CLIENT_ID"],
            "client_secret": os.environ["CLIENT_SECRET"],
            "code": code,
        },
    ).json()
    auth_table.insert(token_response | {"timestamp": time.time()})
    logger.info("Authentication successfully completed")
    return Response(
        status_code=status_codes.HTTP_200_OK,
        headers={"Content-Type": "text/plain"},
        body="Authentication successful",
    )


@app.startup_handler
async def start_refresh():
    asyncio.create_task(access_token_loop())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", default=8001)
    args = parser.parse_args()
    oauth_messages()
    app.start(port=args.port)


if __name__ == "__main__":
    main()
