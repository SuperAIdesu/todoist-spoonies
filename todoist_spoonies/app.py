import argparse
import asyncio
import base64
import hashlib
import hmac
import logging
import os
import signal
import time
import aiohttp
import ids
from aiohttp import web
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
)
from tinydb import Query, TinyDB

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())
logger.handlers[0].setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)

load_dotenv()
# state string used for Todoist API verification
STATE = ids.produce_state_str()

# Telegram bot
bot = ApplicationBuilder().token(os.environ["TELEGRAM_BOT_TOKEN"]).updater(None).build()

db = TinyDB("data/db.json")
auth_table = db.table("auth")

client_session: aiohttp.ClientSession | None = None


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
        async with client_session.post(
            url="https://api.todoist.com/oauth/access_token",
            data={
                "client_id": os.environ["CLIENT_ID"],
                "grant_type": "refresh_token",
                "refresh_token": recent_refresh_token,
                "client_secret": os.environ["CLIENT_SECRET"],
            },
        ) as resp:
            token_response = await resp.json()
        auth_table.insert(token_response | {"timestamp": time.time()})
        # clean old table entries
        auth_table.remove(Query().timestamp < time.time() - 18000)
        logger.info("Token refresh success!")


async def root_auth(request: web.Request):
    """
    Handles Todoist redirected authentication requests
    """
    logger.info("Received redirected authentication request")
    returned_state = request.query.get("state", "")
    if returned_state != STATE:
        return web.Response(status=400, text="Invalid STATE param received")
    code = request.query.get("code", "")
    async with client_session.post(
        url="https://api.todoist.com/oauth/access_token",
        data={
            "client_id": os.environ["CLIENT_ID"],
            "client_secret": os.environ["CLIENT_SECRET"],
            "code": code,
        },
    ) as resp:
        token_response = await resp.json()
    auth_table.insert(token_response | {"timestamp": time.time()})
    logger.info("Authentication successfully completed")
    return web.Response(status=200, text="Authentication successful")


async def todoist_webhook(request: web.Request):
    """
    Receive and process the webhook POST requests from Todoist.
    """
    # verify request validity
    user_agent = request.headers.get("User-Agent")
    if user_agent != "Todoist-Webhooks":
        return web.Response(status=400, text="Invalid User-Agent")

    provided_hmac = request.headers.get("X-Todoist-Hmac-SHA256")
    if not provided_hmac:
        return web.Response(status=400, text="Missing X-Todoist-Hmac-SHA256 header")

    payload = await request.read()
    expected_hmac = base64.b64encode(
        hmac.new(
            os.environ["CLIENT_SECRET"].encode("utf-8"), payload, hashlib.sha256
        ).digest()
    ).decode("utf-8")

    if not hmac.compare_digest(provided_hmac, expected_hmac):
        return web.Response(status=401, text="Invalid HMAC signature")

    # TODO: logic for processing Todoist webhook
    logger.info(await request.json())

    return web.Response(status=200, text="Notification processed")


async def telegram_webhook(request: web.Request):
    """Handle incoming Telegram updates by putting them into the `update_queue`"""
    data = await request.json()
    await bot.update_queue.put(Update.de_json(data=data, bot=bot.bot))
    return web.Response(status=200, text="Notification processed")


async def start(update: Update) -> None:
    await update.message.reply_html(text="hello")


def create_app():
    """
    Creates the HTTP server with routes
    """
    app = web.Application()
    app.router.add_get("/", root_auth)
    app.router.add_post("/todoist/webhook", todoist_webhook)
    app.router.add_post("/telegram/webhook", telegram_webhook)
    return app


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=8001)
    args = parser.parse_args()

    # print the oauth messages first
    oauth_messages()

    # start the bot
    bot.add_handler(CommandHandler("start", start))
    await bot.bot.set_webhook(
        url=f"{os.environ['URL']}/telegram/webhook", allowed_updates=Update.ALL_TYPES
    )
    await bot.initialize()
    await bot.start()

    # refresh Todoist token in background
    asyncio.create_task(access_token_loop())

    # HTTP client session
    global client_session
    client_session = aiohttp.ClientSession()

    # web server setup
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", args.port)
    await site.start()
    logger.info(f"HTTP server started on 0.0.0.0:{args.port}")

    # shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()

    await client_session.close()
    await runner.cleanup()
    await bot.stop()
    await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
