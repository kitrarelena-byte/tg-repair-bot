import asyncio
import logging
import os
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bot import run_bot

# --- IPARTS ---
import requests
from bs4 import BeautifulSoup

# --- PLAYWRIGHT OPTIONAL ---
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except:
    PLAYWRIGHT_AVAILABLE = False

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
CACHE = {}

# ---------- MODELS ----------
class ReportIn(BaseModel):
    telegram_id: str
    type: str
    model: str
    purchase_price: float = 0
    repair_cost: float = 0
    sell_price: float = 0

class AuthIn(BaseModel):
    telegram_id: str
    username: str
    password: str

# ---------- APP ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(safe_bot())
    yield

app = FastAPI(lifespan=lifespan)

# ---------- STATIC ----------
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")

# ---------- PASSWORD HASH ----------
def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

# ---------- REGISTER ----------
@app.post("/register")
async def register(data: AuthIn):

    tg_id = str(data.telegram_id)

    if tg_id in USERS:
        return {
            "ok": False,
            "message": "Пользователь уже существует"
        }

    USERS[tg_id] = {
        "username": data.username,
        "password": hash_password(data.password),
        "role": "admin" if len(USERS) == 0 else "user",
        "created_at": datetime.utcnow().isoformat()
    }

    return {
        "ok": True,
        "user": USERS[tg_id]
    }

# ---------- LOGIN ----------
@app.post("/login")
async def login(data: AuthIn):

    tg_id = str(data.telegram_id)

    user = USERS.get(tg_id)

    if not user:
        return {
            "ok": False,
            "message": "Пользователь не найден"
        }

    if user["password"] != hash_password(data.password):
        return {
            "ok": False,
            "message": "Неверный пароль"
        }

    return {
        "ok": True,
        "user": user
    }

# ---------- REPORT ----------
@app.post("/report")
async def create_report(data: ReportIn):

    if data.type == "sale":
        profit = data.sell_price - data.purchase_price - data.repair_cost

    elif data.type == "repair":
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

# ---------- ANALYTICS ----------
@app.get("/analytics")
async def analytics():

    sales = [r for r in REPORTS if r["type"] == "sale"]
    repairs = [r for r in REPORTS if r["type"] == "repair"]

    return {
        "sales_profit": sum(r["profit"] for r in sales),
        "repairs_profit": sum(r["profit"] for r in repairs),
        "total_profit": sum(r["profit"] for r in REPORTS)
    }

# ---------- REPORTS ----------
@app.get("/reports")
async def get_reports():
    return REPORTS

# ---------- CLEAR REPORTS ----------
@app.delete("/reports/clear")
async def clear_reports():

    REPORTS.clear()

    return {
        "ok": True
    }

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

# ---------- IPARTS SEARCH ----------
@app.get("/parts/search")
async def search_parts(q: str):

    q = q.strip().lower()

    if q in CACHE:
        return CACHE[q]

    # ---------- REQUESTS ----------
    try:

        url = f"https://iparts.by/search/?q={q}"

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        r = requests.get(url, headers=headers, timeout=10)

        soup = BeautifulSoup(r.text, "html.parser")

        items = []

        for el in soup.find_all("div"):

            text = el.get_text(" ", strip=True)

            if "BYN" in text and len(text) < 200:

                items.append({
                    "name": text[:100],
                    "price": text.split()[-1]
                })

            if len(items) >= 10:
                break

        if items:
            CACHE[q] = items
            return items

    except Exception as e:
        logger.warning(e)

    # ---------- PLAYWRIGHT ----------
    if PLAYWRIGHT_AVAILABLE:

        try:

            async with async_playwright() as p:

                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage"
                    ]
                )

                page = await browser.new_page()

                await page.goto(
                    f"https://iparts.by/search/?q={q}",
                    timeout=60000
                )

                await page.wait_for_timeout(5000)

                elements = await page.query_selector_all("div")

                items = []

                for el in elements:

                    text = await el.inner_text()

                    if "BYN" in text and len(text) < 200:

                        lines = text.split("\n")

                        if len(lines) >= 2:

                            items.append({
                                "name": lines[0],
                                "price": lines[-1]
                            })

                    if len(items) >= 10:
                        break

                await browser.close()

                if items:
                    CACHE[q] = items
                    return items

        except Exception as e:
            logger.exception(e)

    # ---------- FALLBACK ----------
    return [
        {
            "name": f"{q} (iparts не дал данные)",
            "price": "—"
        }
    ]

# ---------- RUN ----------
if __name__ == "__main__":

    import uvicorn

    port = int(os.getenv("PORT", 8000))

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port
    )