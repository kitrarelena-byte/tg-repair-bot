import os
import json
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ---------- START ----------
@dp.message(CommandStart())
async def start(message: types.Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📱 Открыть приложение",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            ]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "🚀 Открой мини приложение:",
        reply_markup=kb
    )

# ---------- MINI APP DATA ----------
@dp.message(lambda message: message.web_app_data is not None)
async def webapp_handler(message: types.Message):
    data = json.loads(message.web_app_data.data)

    model = data.get("model")
    repair = data.get("repair")
    sell = data.get("sell")

    try:
        profit = int(sell) - int(repair)
    except:
        profit = "ошибка"

    await message.answer(
        f"📊 Отчет:\n\n"
        f"📱 Модель: {model}\n"
        f"🔧 Ремонт: {repair}\n"
        f"💰 Продажа: {sell}\n"
        f"📈 Чистыми: {profit}"
    )

# ---------- RUN ----------
async def run_bot():
    print("🤖 BOT POLLING START")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)