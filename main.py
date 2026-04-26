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


# ---------- BOT ----------
async def safe_bot():
    try:
        logger.info("🤖 BOT START...")
        await run_bot()
    except Exception as e:
        logger.exception(f"BOT ERROR: {e}")


# ---------- STORAGE ----------
USERS = {}
REPORTS = []


# ---------- MODEL ----------
class ReportIn(BaseModel):
    telegram_id: str
    type: str
    model: str
    purchase_price: float = 0
    repair_cost: float = 0
    sell_price: float = 0


# ---------- LIFESPAN ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(safe_bot())
    yield


app = FastAPI(lifespan=lifespan)


# ---------- STATIC ----------
STATIC_DIR = "static"
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


# ---------- REGISTER ----------
@app.post("/register")
async def register(data: dict):
    tg_id = str(data.get("telegram_id"))

    if tg_id not in USERS:
        USERS[tg_id] = {
            "role": "admin" if len(USERS) == 0 else "user"
        }

    return USERS[tg_id]


# ---------- REPORT ----------
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

    return {"ok": True, "profit": profit}


# ---------- ANALYTICS (FIXED) ----------
@app.get("/analytics")
async def analytics():

    sales = [r for r in REPORTS if r["type"] == "sale"]
    repairs = [r for r in REPORTS if r["type"] == "repair"]

    sales_profit = sum(
        float(r["sell_price"]) - float(r["purchase_price"]) - float(r["repair_cost"])
        for r in sales
    )

    repairs_profit = sum(float(r["profit"]) for r in repairs)

    total_profit = sales_profit + repairs_profit

    return {
        "sales_profit": sales_profit,
        "repairs_profit": repairs_profit,
        "total_profit": total_profit
    }


# ---------- REPORTS ----------
@app.get("/reports")
async def get_reports():
    return REPORTS


# ---------- ADMIN ----------
@app.get("/admin")
async def admin():
    return {
        "users": USERS,
        "reports": REPORTS
    }


# ---------- HEALTH ----------
@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------- RUN ----------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )