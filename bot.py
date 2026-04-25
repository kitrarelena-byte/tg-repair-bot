import os
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

bot = Bot(token=TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer("🚀 Бот работает!")


async def run_bot():
    print("🤖 RUN_BOT ENTERED")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("🧹 WEBHOOK CLEARED")

        await dp.start_polling(bot)

    except Exception as e:
        print("💥 POLLING ERROR:", e)

    finally:
        await bot.session.close()