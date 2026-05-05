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

# --- ДЛЯ IPARTS ---
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

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
    purchase_price: float = 0   # запчасти
    repair_cost: float = 0      # работа
    sell_price: float = 0

# ---------- APP ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(safe_bot())
    yield

app = FastAPI(lifespan=lifespan)

# ---------- STATIC (ВАЖНО: НЕ ЛОМАЕМ) ----------
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")

# ---------- REGISTER (ИСПРАВЛЕНО 405) ----------
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

    # 🔥 ЛОГИКА ПРИБЫЛИ (ИСПРАВЛЕНО)
    if data.type == "sale":
        profit = data.sell_price - data.purchase_price - data.repair_cost

    elif data.type == "repair":
        # ремонт = заработал на работе - потратил на запчасти
        profit = data.repair_cost - data.purchase_price

    else:
        profit = 0

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

# ---------- ANALYTICS (ИСПРАВЛЕНО undefined) ----------
@app.get("/analytics")
async def analytics():

    sales = [r for r in REPORTS if r["type"] == "sale"]
    repairs = [r for r in REPORTS if r["type"] == "repair"]

    return {
        "sales_profit": sum(r["profit"] for r in sales),
        "repairs_profit": sum(r["profit"] for r in repairs),
        "total_profit": sum(r["profit"] for r in REPORTS)
    }

# ---------- REPORT LIST ----------
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

# ---------- HEALTH (чтобы Railway не орал) ----------
@app.get("/health")
async def health():
    return {"status": "ok"}

# ---------- IPARTS ПОИСК ----------
@app.get("/parts/search")
async def search_parts(q: str):

    try:
        url = f"https://iparts.by/search/?q={q}"

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        r = requests.get(url, headers=headers, timeout=10)

        soup = BeautifulSoup(r.text, "html.parser")

        items = []

        # пробуем разные варианты верстки
        products = soup.find_all("div")

        for el in products:
            text = el.get_text(" ", strip=True)

            if "BYN" in text and len(text) < 200:
                items.append({
                    "name": text[:80],
                    "price": text.split()[-1]
                })

            if len(items) >= 10:
                break

        # если сайт ничего не дал
        if not items:
            return [
                {"name": f"{q} (пример)", "price": "100"},
                {"name": f"{q} (пример 2)", "price": "200"}
            ]

        return items

    except Exception as e:
        logger.exception(e)
        return [
            {"name": f"{q} (ошибка поиска)", "price": "—"}
        ]

# ---------- RUN ----------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000))
    )