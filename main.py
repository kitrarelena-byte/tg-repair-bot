import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ДОБАВИЛ
import requests
from bs4 import BeautifulSoup

from bot import run_bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

logger.info("🚀 MAIN STARTED")

# ---------- BOT ----------
async def safe_bot():
    try:
        await run_bot()
    except Exception as e:
        logger.exception(e)

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

# ---------- REGISTER ----------
@app.post("/register")
async def register(data: dict):
    tg_id = str(data.get("telegram_id"))

    if tg_id not in USERS:
        USERS[tg_id] = {
            "username": data.get("username", "unknown"),
            "role": "admin" if len(USERS) == 0 else "user",
            "created_at": datetime.utcnow().isoformat()
        }

    return USERS[tg_id]

# ---------- REPORT ----------
@app.post("/report")
async def create_report(data: ReportIn):

    # ВАЖНО: правильная логика
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

# ---------- ANALYTICS ----------
@app.get("/analytics")
async def analytics():

    sales = [r for r in REPORTS if r["type"] == "sale"]
    repairs = [r for r in REPORTS if r["type"] == "repair"]

    sales_profit = sum(r["profit"] for r in sales)
    repairs_profit = sum(r["profit"] for r in repairs)

    return {
        "sales_profit": sales_profit,
        "repairs_profit": repairs_profit,
        "total_profit": sales_profit + repairs_profit
    }

# ---------- ADMIN ----------
@app.get("/admin")
async def admin():
    return {
        "users": USERS,
        "reports": REPORTS
    }

# ---------- IPARTS SEARCH (НОВОЕ) ----------
@app.get("/parts/search")
async def search_parts(q: str):

    try:
        url = f"https://iparts.by/search/?q={q}"
        headers = {"User-Agent": "Mozilla/5.0"}

        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        items = []

        # ⚠️ селекторы могут меняться — но сейчас рабочие
        for el in soup.select(".product-item")[:10]:
            name = el.select_one(".product-title")
            price = el.select_one(".price")

            if name and price:
                items.append({
                    "name": name.text.strip(),
                    "price": price.text.strip()
                })

        return items

    except Exception as e:
        logger.exception(e)
        return []

# ---------- HEALTH ----------
@app.get("/health")
async def health():
    return {"status": "ok"}

# ---------- RUN ----------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))