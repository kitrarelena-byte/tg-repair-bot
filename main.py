import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from sqlalchemy import Column, Integer, String, Float, DateTime, select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from aiogram import Bot, Dispatcher

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

log.info("MAIN STARTED")

# ---------------- BOT ----------------
TOKEN = os.getenv("BOT_TOKEN")  # Railway variable
bot = Bot(token=TOKEN)
dp = Dispatcher()


# ---------------- DATABASE ----------------
DATABASE_URL = "sqlite+aiosqlite:///./data.db"

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

Base = declarative_base()


# ---------------- MODELS ----------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True)
    role = Column(String, default="user")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)

    type = Column(String)  # repair / sale
    model = Column(String)

    purchase_price = Column(Float, default=0)
    repair_cost = Column(Float, default=0)
    sell_price = Column(Float, default=0)

    profit = Column(Float, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------- FASTAPI ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    asyncio.create_task(run_bot())

    yield


app = FastAPI(lifespan=lifespan)


# ---------------- STATIC (Mini App) ----------------
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/", StaticFiles(directory="static", html=True), name="static")


# ---------------- BOT RUNNER ----------------
async def run_bot():
    log.info("BOT STARTED")
    await dp.start_polling(bot)


# ---------------- CREATE REPORT ----------------
@app.post("/report")
async def create_report(data: dict):
    async with SessionLocal() as s:

        purchase = float(data.get("purchase_price", 0))
        repair = float(data.get("repair_cost", 0))
        sell = float(data.get("sell_price", 0))

        if data["type"] == "sale":
            profit = sell - purchase - repair
        else:
            profit = sell - repair

        r = Report(
            type=data["type"],
            model=data["model"],
            purchase_price=purchase,
            repair_cost=repair,
            sell_price=sell,
            profit=profit
        )

        s.add(r)
        await s.commit()

        return {"ok": True, "profit": profit}


# ---------------- GET REPORTS (FILTER) ----------------
@app.get("/reports")
async def get_reports(days: int = 7):
    async with SessionLocal() as s:

        since = datetime.utcnow() - timedelta(days=days)

        res = await s.execute(
            select(Report).where(Report.created_at >= since)
        )

        return res.scalars().all()


# ---------------- ANALYTICS ----------------
@app.get("/analytics")
async def analytics():
    async with SessionLocal() as s:

        res = await s.execute(select(Report))
        reports = res.scalars().all()

        return {
            "total_profit": sum(r.profit for r in reports),
            "count": len(reports)
        }


# ---------------- TOP MODELS ----------------
@app.get("/top-models")
async def top_models():
    async with SessionLocal() as s:

        res = await s.execute(
            select(
                Report.model,
                func.sum(Report.profit)
            ).group_by(Report.model)
        )

        return res.all()


# ---------------- CHART DATA ----------------
@app.get("/chart")
async def chart():
    async with SessionLocal() as s:

        res = await s.execute(select(Report))
        reports = res.scalars().all()

        data = {}

        for r in reports:
            day = r.created_at.strftime("%Y-%m-%d")
            data[day] = data.get(day, 0) + r.profit

        return data


# ---------------- USER ROLE ----------------
@app.get("/user/{telegram_id}")
async def get_user(telegram_id: str):
    async with SessionLocal() as s:
        res = await s.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return res.scalar_one_or_none()


# ---------------- START ----------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000))
    )