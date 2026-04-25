import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from sqlalchemy import select

from bot import run_bot
from database import engine, SessionLocal
from models import Base, Part, Report

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("🚀 MAIN STARTED")


# ---------------- BOT ----------------
async def safe_bot():
    try:
        logger.info("🤖 BOT START")
        await run_bot()
    except Exception as e:
        logger.exception(e)


# ---------------- LIFESPAN ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔥 STARTUP")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    asyncio.create_task(safe_bot())

    yield

    logger.info("🛑 SHUTDOWN")


app = FastAPI(lifespan=lifespan)


# ---------------- STATIC ----------------
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/", StaticFiles(directory="static", html=True), name="static")


# ---------------- API: PARTS ----------------
@app.get("/parts")
async def get_parts():
    async with SessionLocal() as s:
        res = await s.execute(select(Part))
        return res.scalars().all()


@app.post("/parts")
async def add_part(data: dict):
    async with SessionLocal() as s:
        s.add(Part(name=data["name"], price=int(data["price"])))
        await s.commit()
        return {"ok": True}


# ---------------- API: REPORT ----------------
@app.post("/report")
async def report(data: dict):
    async with SessionLocal() as s:

        if data["type"] == "sale":
            profit = int(data["sell"]) - int(data["buy"]) - int(data["repair"])
        else:
            profit = int(data["price"])

        r = Report(
            type=data["type"],
            model=data["model"],
            buy=int(data.get("buy", 0)),
            repair=int(data.get("repair", 0)),
            sell=int(data.get("sell", 0)),
            profit=profit,
            date=datetime.now().strftime("%Y-%m-%d")
        )

        s.add(r)
        await s.commit()

        return {"profit": profit}


# ---------------- API: ANALYTICS ----------------
@app.get("/analytics")
async def analytics():
    async with SessionLocal() as s:
        res = await s.execute(select(Report))
        reports = res.scalars().all()

        return {
            "total": sum(r.profit for r in reports),
            "count": len(reports)
        }


# ---------------- RUN ----------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000))
    )