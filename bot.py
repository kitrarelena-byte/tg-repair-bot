import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import WebAppInfo
from aiogram.filters import CommandStart
import asyncio

TOKEN = os.getenv("BOT_TOKEN")
print("TOKEN =", TOKEN)
bot = Bot(token=TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(msg: types.Message):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(
                text="📊 Открыть приложение",
                web_app=WebAppInfo(url=os.getenv("WEBAPP_URL"))
            )]
        ],
        resize_keyboard=True
    )

    await msg.answer("Открой мини-приложение:", reply_markup=kb)


async def run_bot():
    await dp.start_polling(bot)