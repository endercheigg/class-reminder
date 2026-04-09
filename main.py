import asyncio
import os
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
import discord

from database import init_db
from telegram_bot import (
    start, help_command, link, timezone_command,
    next_class, schedule, delete, add, move, config, join,
    handle_message,
)
from discord_bot import setup_discord_handlers
from scheduler import start_scheduler

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DISCORD_TOKEN  = os.getenv("DISCORD_TOKEN")

print("Bots are starting...")
init_db()

telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

telegram_app.add_handler(CommandHandler("start",    start))
telegram_app.add_handler(CommandHandler("help",     help_command))
telegram_app.add_handler(CommandHandler("link",     link))
telegram_app.add_handler(CommandHandler("timezone", timezone_command))
telegram_app.add_handler(CommandHandler("next",     next_class))
telegram_app.add_handler(CommandHandler("schedule", schedule))
telegram_app.add_handler(CommandHandler("delete",   delete))
telegram_app.add_handler(CommandHandler("add",      add))
telegram_app.add_handler(CommandHandler("move",     move))
telegram_app.add_handler(CommandHandler("config",   config))
telegram_app.add_handler(CommandHandler("join",     join))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)

setup_discord_handlers(discord_client)


async def main():
    async with telegram_app:
        await telegram_app.start()
        await telegram_app.updater.start_polling()

        start_scheduler(telegram_app, discord_client)

        print("Bots are running!")

        try:
            await discord_client.start(DISCORD_TOKEN)
        finally:
            await telegram_app.updater.stop()
            await telegram_app.stop()


if __name__ == "__main__":
    asyncio.run(main())