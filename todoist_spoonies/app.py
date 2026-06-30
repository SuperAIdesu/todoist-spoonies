import argparse
import asyncio
import base64
import hashlib
import hmac
import logging
import os
import signal

from aiohttp import web
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, TypeHandler
from scheduler import daily_summary_loop
from tg_bot_handlers import daily_summary, filter_user_callback, health, recent_days, today
from tinydb import TinyDB
from todoist_auth import access_token_loop, produce_state_str, token_exchange
from todoist_notifs import process_event

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())
logger.handlers[0].setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)

load_dotenv()
# state string used for Todoist API verification
STATE = produce_state_str()

# Telegram bot
bot = ApplicationBuilder().token(os.environ["TELEGRAM_BOT_TOKEN"]).updater(None).build()

db = TinyDB("data/db.json")
auth_table = db.table("auth")


async def handle_root_auth(request: web.Request):
    """
    Handles Todoist redirected authentication requests
    """
    logger.info("Received redirected authentication request")
    returned_state = request.query.get("state", "")
    if returned_state == "":
        return web.Response(status=400)
    if returned_state != STATE:
        return web.Response(status=400, text="Invalid STATE param received")
    try:
        await token_exchange(request.query.get("code", ""))
    except Exception as e:
        logger.error("Token exchange failed!")
        logger.error(e)
    logger.info("Authentication successfully completed")
    return web.Response(status=200, text="Authentication successful")


async def handle_todoist_webhook(request: web.Request):
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

    try:
        await process_event(await request.json())
    except Exception as e:
        logger.error("Notification processing failed!")
        logger.error(e)

    return web.Response(status=200, text="Notification processed")


async def handle_telegram_webhook(request: web.Request):
    """Handle incoming Telegram updates by putting them into the `update_queue`"""
    data = await request.json()
    await bot.update_queue.put(Update.de_json(data=data, bot=bot.bot))
    return web.Response(status=200, text="Notification processed")


def create_app():
    """
    Creates the HTTP server with routes
    """
    app = web.Application()
    app.router.add_get("/", handle_root_auth)
    app.router.add_post("/todoist/webhook", handle_todoist_webhook)
    app.router.add_post("/telegram/webhook", handle_telegram_webhook)
    return app


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--listen", default="127.0.0.1")
    parser.add_argument("-p", "--port", type=int, default=8001)
    args = parser.parse_args()

    # print the oauth messages first
    logger.info("Initializing OAuth workflow... Open the below URL:")
    logger.info(
        f"https://app.todoist.com/oauth/authorize?client_id={os.environ['CLIENT_ID']}&scope=data:read_write&state={STATE}"
    )

    # start the bot
    bot.add_handler(TypeHandler(Update, filter_user_callback), -1)
    bot.add_handler(CommandHandler("health", health))
    bot.add_handler(CommandHandler("today", callback=today))
    bot.add_handler(CommandHandler("daily_summary", callback=daily_summary))
    bot.add_handler(CommandHandler("recent_days", callback=recent_days))
    await bot.bot.set_webhook(
        url=f"{os.environ['URL']}/telegram/webhook", allowed_updates=Update.ALL_TYPES
    )
    await bot.initialize()
    await bot.start()

    # refresh Todoist token in background
    asyncio.create_task(access_token_loop())
    asyncio.create_task(daily_summary_loop(bot.bot))

    # web server setup
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.listen, args.port)
    await site.start()
    logger.info(f"HTTP server started on {args.listen}:{args.port}")

    # shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()

    await runner.cleanup()
    await bot.stop()
    await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
