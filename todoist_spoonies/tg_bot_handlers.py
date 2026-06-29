from telegram import Update
from telegram.ext import (
    ContextTypes,
)


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        chat_id = update.effective_chat.id
    else:
        return
    await context.bot.send_message(chat_id=chat_id, text="This bot is running.")
