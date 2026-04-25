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


@dp.message(CommandStart())
async def start(message: types.Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📱 Открыть CRM",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            ]
        ],
        resize_keyboard=True
    )

    await message.answer("🚀 Открой CRM:", reply_markup=kb)


@dp.message(lambda message: message.web_app_data is not None)
async def webapp_handler(message: types.Message):
    data = json.loads(message.web_app_data.data)

    type_ = data.get("type")

    if type_ == "sale":
        profit = int(data["sell"]) - int(data["repair"])

        text = (
            f"📊 Продажа\n\n"
            f"📱 {data['model']}\n"
            f"🔧 Ремонт: {data['repair']}\n"
            f"💰 Продажа: {data['sell']}\n"
            f"📈 Чистыми: {profit}"
        )

    elif type_ == "repair":
        parts = ", ".join(data["parts"])

        text = (
            f"🛠 Ремонт\n\n"
            f"📱 {data['model']}\n"
            f"🔩 Запчасти: {parts}\n"
            f"💰 Цена: {data['price']}"
        )

    else:
        text = "⚠️ Неизвестный тип отчета"

    await message.answer(text)


async def run_bot():
    print("🤖 BOT STARTED")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)