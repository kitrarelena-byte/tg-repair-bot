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

# ---------------- LOG ----------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")
log.info("MAIN STARTED")

# ---------------- BOT ----------------
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher()

# ---------------- DB ----------------
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

    if bot:
        asyncio.create_task(run_bot())

    yield


app = FastAPI(lifespan=lifespan)


# ---------------- STATIC MINI APP ----------------
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/", StaticFiles(directory="static", html=True), name="static")


# ---------------- BOT ----------------
async def run_bot():
    log.info("BOT STARTED")
    if bot:
        await dp.start_polling(bot)


# ---------------- SAFE REPORT (НЕ ПАДАЕТ) ----------------
@app.post("/report")
async def create_report(data: dict):
    try:
        async with SessionLocal() as s:

            purchase = float(data.get("purchase_price") or 0)
            repair = float(data.get("repair_cost") or 0)
            sell = float(data.get("sell_price") or 0)

            if data.get("type") == "sale":
                profit = sell - purchase - repair
            else:
                profit = sell - repair

            r = Report(
                type=data.get("type"),
                model=data.get("model"),
                purchase_price=purchase,
                repair_cost=repair,
                sell_price=sell,
                profit=profit
            )

            s.add(r)
            await s.commit()

            return {
                "ok": True,
                "profit": profit,
                "net_profit": profit
            }

    except Exception as e:
        log.exception(e)
        return {"ok": False, "error": str(e)}


# ---------------- REPORTS WITH FILTER ----------------
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


# ---------------- DAY/WEEK ANALYTICS ----------------
@app.get("/analytics/time")
async def analytics_time():
    async with SessionLocal() as s:

        res = await s.execute(select(Report))
        reports = res.scalars().all()

        now = datetime.utcnow()
        day = now - timedelta(days=1)
        week = now - timedelta(days=7)

        return {
            "day_profit": sum(r.profit for r in reports if r.created_at >= day),
            "week_profit": sum(r.profit for r in reports if r.created_at >= week)
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


# ---------------- CHART DATA (Chart.js) ----------------
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


# ---------------- USERS + ROLES ----------------
@app.get("/user/{telegram_id}")
async def get_user(telegram_id: str):
    async with SessionLocal() as s:
        res = await s.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return res.scalar_one_or_none()


# ---------------- HEALTH CHECK ----------------
@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------- SAFE START ----------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000))
    )