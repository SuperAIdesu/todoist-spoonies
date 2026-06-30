import logging
import os
from datetime import datetime, time

from records import DailySummaryConfig, build_today_message, get_records_by_time
from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

logger = logging.getLogger(__name__)


async def filter_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Only allow specific user, stopping other handlers otherwise.
    """
    user_id = os.environ["TELEGRAM_USER_ID"]
    if user_id == "":
        logger.error("TELEGRAM_USER_ID not set, the bot won't be useful!")
        raise ApplicationHandlerStop
    assert update.effective_user
    assert update.effective_message
    if str(update.effective_user.id) == user_id:
        pass
    else:
        await update.effective_message.reply_text(
            "You are not authorized to use this bot!"
        )
        logger.info(
            f"Unauthorized message from id {update.effective_user.id}. Allowed user: {user_id}"
        )
        raise ApplicationHandlerStop


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Health check for the bot.
    """
    assert update.effective_chat
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text="This bot is running."
    )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Send a summary of today's completed tasks, and total spoon count.
    """
    assert update.effective_message
    assert update.effective_user
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    records = get_records_by_time(start, end)
    summary_msg = build_today_message(records)
    greetings_line = (
        f"Hi {update.effective_user.first_name} {update.effective_user.last_name},\n"
    )
    await update.effective_message.reply_text(
        greetings_line + summary_msg, parse_mode="MarkdownV2"
    )


async def daily_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Enable/disable scheduled daily summary.
    Usage: /daily_summary enable HH:MM | /daily_summary disable | /daily_summary
    """
    assert update.effective_message
    args = context.args
    config = DailySummaryConfig.load()

    if not args:
        match config.enabled:
            case True:
                await update.effective_message.reply_text(
                    f"Daily summary is enabled at {config.scheduled_time.strftime('%H:%M')}."
                )
                return
            case _:
                await update.effective_message.reply_text(
                    "Daily summary is not enabled."
                )
                return

    command = args[0].lower()

    match command:
        case "enable":
            if len(args) < 2:
                await update.effective_message.reply_text(
                    "Usage: /daily_summary enable HH:MM"
                )
                return
            try:
                h, m = args[1].split(":")
                h, m = int(h), int(m)
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    raise ValueError
                config.enabled = True
                config.scheduled_time = time(h, m)
                config.save()
                await update.effective_message.reply_text(
                    f"Daily summary enabled at {config.scheduled_time.strftime('%H:%M')}."
                )
            except ValueError, IndexError:
                await update.effective_message.reply_text(
                    "Invalid time format. Usage: /daily_summary enable HH:MM"
                )
        case "disable":
            config.enabled = False
            config.save()
            await update.effective_message.reply_text("Daily summary disabled.")
        case _:
            await update.effective_message.reply_text(
                "Usage:\n/daily_summary enable HH:MM\n/daily_summary disable\n/daily_summary"
            )
