import asyncio
import logging
import os
from datetime import datetime

from records import DailySummaryConfig, build_today_message, get_records_by_time
from telegram import Bot

logger = logging.getLogger(__name__)


async def daily_summary_loop(bot: Bot):
    """Background loop that sends daily summary at configured time."""
    user_id = os.environ["TELEGRAM_USER_ID"]
    if user_id == "":
        logger.warning("TELEGRAM_USER_ID not set, the bot will not work!")
    while True:
        config = DailySummaryConfig.load()
        if not config.enabled:
            await asyncio.sleep(60)
            continue

        now = datetime.now()
        target = now.replace(
            hour=config.scheduled_time.hour,
            minute=config.scheduled_time.minute,
            second=0,
            microsecond=0,
        )
        if target <= now:
            from datetime import timedelta

            target = target + timedelta(days=1)

        wait_secs = (target - now).total_seconds()
        logger.info(f"Daily summary scheduled for {target}, sleeping {wait_secs:.0f}s")
        await asyncio.sleep(wait_secs)

        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        records = get_records_by_time(start, end)
        message = build_today_message(records)
        await bot.send_message(chat_id=user_id, text=message, parse_mode="MarkdownV2")
        logger.info("Daily summary sent")
