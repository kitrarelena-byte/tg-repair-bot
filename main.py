import asyncio
from fastapi import FastAPI
from fastapi.responses import FileResponse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from config import BOT_TOKEN, BASE_URL
from services import create_report, get_reports, analytics, get_or_create_user
from database import engine, Base

app = FastAPI()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# --- INIT DB ---
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# --- WEBAPP ---
@app.get("/")
async def index():
    return FileResponse("webapp/index.html")


@app.get("/app.js")
async def js():
    return FileResponse("webapp/app.js")


@app.get("/style.css")
async def css():
    return FileResponse("webapp/style.css")


# --- API ---
@app.get("/reports/{user_id}")
async def reports(user_id: int):
    data = await get_reports(user_id)
    return [{"model": r.model, "profit": r.profit} for r in data]


@app.get("/analytics/{user_id}")
async def stats(user_id: int):
    return await analytics(user_id)


# --- BOT ---
@dp.message(Command("start"))
async def start(msg: types.Message):
    await get_or_create_user(msg.from_user.id)

    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(
                text="📊 Открыть приложение",
                web_app=types.WebAppInfo(url=BASE_URL)
            )]
        ],
        resize_keyboard=True
    )

    await msg.answer("Готово", reply_markup=kb)


@dp.message(Command("report"))
async def report(msg: types.Message):
    try:
        _, model, repair, sell = msg.text.split()

        r = await create_report(
            msg.from_user.id,
            model,
            float(repair),
            float(sell)
        )

        await msg.answer(f"{model} прибыль: {r.profit}")
    except:
        await msg.answer("Формат: /report iphone11 50 120")


# --- START ---
async def start_all():
    await init_db()

    asyncio.create_task(dp.start_polling(bot))

    import uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(start_all())