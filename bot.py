import os
import asyncio
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# -----------------------
# LOGGING (очень важно)
# -----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# -----------------------
# TOKEN SAFETY CHECK
# -----------------------
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "❌ BOT_TOKEN is missing in environment variables (Railway Variables)"
    )

# -----------------------
# BOT INIT
# -----------------------
bot = Bot(token=TOKEN)
dp = Dispatcher()


# -----------------------
# /START HANDLER
# -----------------------
@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🚀 Бот запущен и работает!\n\n"
        "Выберите действие в Mini App."
    )


# -----------------------
# OPTIONAL: LOG ALL MESSAGES
# -----------------------
@dp.message()
async def echo(message: types.Message):
    logging.info(f"Message from {message.from_user.id}: {message.text}")


# -----------------------
# BOT RUNNER (SAFE)
# -----------------------
async def run_bot():
    logging.info("🤖 Bot is starting polling...")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("🧹 Webhook cleared (if existed)")

        await dp.start_polling(bot)

    except Exception as e:
        logging.exception(f"💥 Bot crashed: {e}")

    finally:
        await bot.session.close()
        logging.info("🛑 Bot stopped cleanly")


# -----------------------
# LOCAL TEST (optional)
# -----------------------
if __name__ == "__main__":
    asyncio.run(run_bot())