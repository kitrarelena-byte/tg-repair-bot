import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bot import run_bot

# ---------- LOG ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

logger.info("🚀 MAIN STARTED")


# ---------- BOT SAFE START ----------
async def safe_bot():
    try:
        logger.info("🤖 BOT START...")
        await run_bot()
    except Exception as e:
        logger.exception(f"BOT ERROR: {e}")


# ---------- MEMORY STORAGE ----------
USERS = {}
REPORTS = []


# ---------- MODELS ----------
class ReportIn(BaseModel):
    telegram_id: str
    type: str  # sale / repair
    model: str
    purchase_price: float = 0
    repair_cost: float = 0
    sell_price: float = 0


# ---------- FASTAPI LIFESPAN ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔥 STARTUP")

    asyncio.create_task(safe_bot())

    yield

    logger.info("🛑 SHUTDOWN")


# ---------- APP ----------
app = FastAPI(lifespan=lifespan)


# ---------- STATIC MINI APP ----------
STATIC_DIR = "static"
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


# ---------- REGISTER USER ----------
@app.post("/register")
async def register(data: dict):
    tg_id = str(data.get("telegram_id"))

    if tg_id not in USERS:
        USERS[tg_id] = {
            "role": "admin" if len(USERS) == 0 else "user"
        }

    return USERS[tg_id]


# ---------- CREATE REPORT ----------
@app.post("/report")
async def create_report(data: ReportIn):
    profit = float(data.sell_price) - float(data.purchase_price) - float(data.repair_cost)

    report = {
        "id": len(REPORTS) + 1,
        "telegram_id": data.telegram_id,
        "type": data.type,
        "model": data.model,
        "purchase_price": data.purchase_price,
        "repair_cost": data.repair_cost,
        "sell_price": data.sell_price,
        "profit": profit,
        "created_at": datetime.utcnow().isoformat()
    }

    REPORTS.append(report)

    logger.info(f"NEW REPORT: {report}")

    return {"ok": True, "profit": profit}


# ---------- ANALYTICS ----------
@app.get("/analytics")
async def analytics():
    total_profit = sum(r["profit"] for r in REPORTS)

    sales = len([r for r in REPORTS if r["type"] == "sale"])
    repairs = len([r for r in REPORTS if r["type"] == "repair"])

    return {
        "total_profit": total_profit,
        "sales_count": sales,
        "repair_count": repairs
    }


# ---------- REPORTS FILTER ----------
@app.get("/reports")
async def get_reports(days: int = 7):
    since = datetime.utcnow() - timedelta(days=days)

    filtered = [
        r for r in REPORTS
        if datetime.fromisoformat(r["created_at"]) >= since
    ]

    return filtered


# ---------- TOP MODELS ----------
@app.get("/top")
async def top_models():
    stats = {}

    for r in REPORTS:
        stats[r["model"]] = stats.get(r["model"], 0) + r["profit"]

    return sorted(stats.items(), key=lambda x: x[1], reverse=True)


# ---------- ADMIN PANEL ----------
@app.get("/admin")
async def admin():
    return {
        "users": USERS,
        "reports": REPORTS
    }


# ---------- HEALTH CHECK ----------
@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------- RUN SERVER ----------
if name == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )