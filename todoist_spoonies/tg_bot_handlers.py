import logging
import os

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
    Return a summary of today's completed tasks, and total spoon count.
    """
    # user bot.reply_markdown_v2() to send message
    pass
