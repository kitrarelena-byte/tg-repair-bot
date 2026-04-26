import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bot import run_bot

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
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/", StaticFiles(directory="static", html=True), name="static")

# ---------- REGISTER / PROFILE ----------
@app.post("/register")
async def register(data: dict):
    tg_id = str(data.get("telegram_id"))
    username = data.get("username", "unknown")

    if tg_id not in USERS:
        USERS[tg_id] = {
            "telegram_id": tg_id,
            "username": username,
            "role": "admin" if len(USERS) == 0 else "user",
            "created_at": datetime.utcnow().isoformat()
        }

    return USERS[tg_id]


@app.get("/me/{tg_id}")
async def me(tg_id: str):
    return USERS.get(tg_id, {"error": "not found"})


@app.get("/users")
async def users():
    return USERS


# ---------- REPORT ----------
@app.post("/report")
async def create_report(data: ReportIn):

    # 🔥 правильная прибыль
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


# ---------- ANALYTICS FIX ----------
@app.get("/analytics")
async def analytics():

    sales = [r for r in REPORTS if r["type"] == "sale"]
    repairs = [r for r in REPORTS if r["type"] == "repair"]

    sales_revenue = sum(r["sell_price"] for r in sales)
    purchase_cost = sum(r["purchase_price"] for r in sales)
    repair_cost = sum(r["repair_cost"] for r in REPORTS)

    total_profit = sum(r["profit"] for r in REPORTS)

    return {
        "sales_revenue": sales_revenue,
        "repair_cost": repair_cost,
        "purchase_cost": purchase_cost,
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


# ---------- RUN ----------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))

    uvicorn.run("main:app", host="0.0.0.0", port=port)