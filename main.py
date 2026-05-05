import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bot import run_bot

import requests
from bs4 import BeautifulSoup

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

# ---------- STATIC FIX ----------
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")

# ---------- REGISTER ----------
@app.post("/register")
async def register(data: dict):
    tg_id = str(data.get("telegram_id"))
    username = data.get("username", "unknown")

    if tg_id not in USERS:
        USERS[tg_id] = {
            "role": "admin" if len(USERS) == 0 else "user",
            "username": username,
            "created_at": datetime.utcnow().isoformat()
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

# ---------- ANALYTICS FIX ----------
@app.get("/analytics")
async def analytics():

    sales = [r for r in REPORTS if r["type"] == "sale"]
    repairs = [r for r in REPORTS if r["type"] == "repair"]

    sales_profit = sum(r["profit"] for r in sales)
    repairs_income = sum(r["repair_cost"] for r in repairs)

    total = sales_profit + repairs_income

    return {
        "sales_profit": sales_profit,
        "repairs_income": repairs_income,
        "total_profit": total
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

# ---------- PARTS SEARCH (IPARTS + FALLBACK) ----------
@app.get("/parts/search")
async def search_parts(q: str):

    try:
        url = f"https://iparts.by/search/?q={q}"

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        res = requests.get(url, headers=headers, timeout=5)

        soup = BeautifulSoup(res.text, "lxml")

        items = []

        for el in soup.select(".b-offer__wrap")[:5]:
            name = el.select_one(".b-offer__name")
            price = el.select_one(".b-offer__price")

            if name and price:
                items.append({
                    "name": name.text.strip(),
                    "price": price.text.strip()
                })

        if items:
            return {"items": items}

    except Exception as e:
        logger.error(f"iparts error: {e}")

    # 🔥 fallback если iparts не дал данные
    return {
        "items": [
            {"name": f"{q} экран", "price": 120},
            {"name": f"{q} батарея", "price": 80},
            {"name": f"{q} камера", "price": 150},
        ]
    }

# ---------- HEALTH ----------
@app.get("/health")
async def health():
    return {"status": "ok"}

# ---------- RUN ----------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000))
    )