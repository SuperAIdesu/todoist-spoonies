import argparse
import asyncio
import base64
import hashlib
import hmac
import logging
import os
import signal
import time

import ids
import requests
from dotenv import load_dotenv
from robyn import Request, Response, Robyn, status_codes
from robyn.exceptions import HTTPException
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
)
from tinydb import Query, TinyDB

logger = logging.getLogger()

load_dotenv()
# state string used for Todoist API verification
STATE = ids.produce_state_str()

# HTTP server
app = Robyn(__file__)
# Telegram bot
bot = ApplicationBuilder().token(os.environ["TELEGRAM_BOT_TOKEN"]).updater(None).build()

db = TinyDB("data/db.json")
auth_table = db.table("auth")


def oauth_messages():
    """
    Print initial messages for the user to start the authentication workflow.
    """
    logger.info("Initializing OAuth workflow... Open the below URL:")
    logger.info(
        f"https://app.todoist.com/oauth/authorize?client_id={os.environ['CLIENT_ID']}&scope=data:read_write&state={STATE}"
    )


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
async def root_auth(request: Request):
    """
    Handles Todoist redirected authentication requests
    """
    logger.info("Received redirected authentication request")
    returned_state = request.query_params.get("state", "")
    if returned_state != STATE:
        raise HTTPException(400, "Invalid STATE param received")
    code = request.query_params.get("code", "")
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


@app.post("/todoist/webhook")
async def todoist_webhook(request: Request):
    """
    Receive and process the webhook POST requests from Todoist.
    """
    # verify request validity
    user_agent = request.headers.get("User-Agent")
    if user_agent != "Todoist-Webhooks":
        raise HTTPException(400, "Invalid User-Agent")

    # verify HMAC signature
    provided_hmac = request.headers.get("X-Todoist-Hmac-SHA256")
    if not provided_hmac:
        raise HTTPException(400, "Missing X-Todoist-Hmac-SHA256 header")

    payload = str(request.body).encode("utf-8")
    expected_hmac = base64.b64encode(
        hmac.new(
            os.environ["CLIENT_SECRET"].encode("utf-8"), payload, hashlib.sha256
        ).digest()
    ).decode("utf-8")

    if not hmac.compare_digest(provided_hmac, expected_hmac):
        raise HTTPException(401, "Invalid HMAC signature")

    # TODO: logic to process requests
    logger.info(request.json())

    return Response(
        status_code=status_codes.HTTP_200_OK,
        headers={"Content-Type": "text/plain"},
        body="Notification processed",
    )


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram updates by putting them into the `update_queue`"""
    await bot.update_queue.put(Update.de_json(data=request.json(), bot=bot.bot))
    return Response(
        status_code=status_codes.HTTP_200_OK,
        headers={"Content-Type": "text/plain"},
        body="Notification processed",
    )


async def start(update: Update) -> None:
    """Display a message with instructions on how to use this bot."""
    await update.message.reply_html(text="hello")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", default=8001)
    args = parser.parse_args()
    oauth_messages()

    bot.add_handler(CommandHandler("start", start))
    await bot.bot.set_webhook(
        url=f"{os.environ['URL']}/telegram/webhook", allowed_updates=Update.ALL_TYPES
    )
    await bot.initialize()
    await bot.start()

    asyncio.create_task(access_token_loop())

    robyn_task = asyncio.create_task(asyncio.to_thread(app.start, port=args.port))

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()

    app.stop()
    robyn_task.cancel()
    await bot.stop()
    await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
