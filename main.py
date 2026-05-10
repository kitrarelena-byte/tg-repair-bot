import asyncio
import logging
import os
import hashlib

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bot import run_bot

# ---------- OPTIONAL PLAYWRIGHT ----------
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except:
    PLAYWRIGHT_AVAILABLE = False

# ---------- OPTIONAL REQUESTS ----------
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# =========================
# ADMIN
# =========================

ADMIN_USERNAME = "appletech752"

# =========================
# APP
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(safe_bot())
    yield

app = FastAPI(lifespan=lifespan)

# =========================
# STATIC
# =========================

if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")

# =========================
# STORAGE
# =========================

USERS = {}
REPORTS = []
CACHE = {}

# =========================
# PASSWORDS
# =========================

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str):
    return hash_password(password) == hashed

# =========================
# BOT
# =========================

async def safe_bot():
    try:
        await run_bot()
    except Exception as e:
        logger.exception(e)

# =========================
# MODELS
# =========================

class ReportIn(BaseModel):
    telegram_id: str
    type: str
    model: str
    purchase_price: float = 0
    repair_cost: float = 0
    sell_price: float = 0

# =========================
# AUTH
# =========================

@app.post("/register")
async def register(data: dict):

    telegram_id = str(data.get("telegram_id"))
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        raise HTTPException(400, "Введите логин и пароль")

    if username in USERS:
        raise HTTPException(400, "Аккаунт уже существует")

    USERS[username] = {
        "telegram_id": telegram_id,
        "username": username,
        "password": hash_password(password),
        "role": "admin" if username == ADMIN_USERNAME else "user",
        "blocked": False,
        "created_at": datetime.utcnow().isoformat()
    }

    return {
        "ok": True,
        "role": USERS[username]["role"]
    }

@app.post("/login")
async def login(data: dict):

    telegram_id = str(data.get("telegram_id"))
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if username not in USERS:
        raise HTTPException(404, "Аккаунт не найден")

    user = USERS[username]

    if user["blocked"]:
        raise HTTPException(403, "Аккаунт заблокирован")

    if not verify_password(password, user["password"]):
        raise HTTPException(401, "Неверный пароль")

    if user["telegram_id"] != telegram_id:
        raise HTTPException(
            403,
            "Этот аккаунт привязан к другому Telegram аккаунту"
        )

    return {
        "ok": True,
        "username": user["username"],
        "role": user["role"]
    }

# =========================
# REPORT
# =========================

@app.post("/report")
async def create_report(data: ReportIn):

    if data.type == "sale":
        profit = (
            data.sell_price
            - data.purchase_price
            - data.repair_cost
        )

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

    return {
        "ok": True,
        "profit": profit
    }

# =========================
# ANALYTICS
# =========================

@app.get("/analytics")
async def analytics():

    sales = [r for r in REPORTS if r["type"] == "sale"]
    repairs = [r for r in REPORTS if r["type"] == "repair"]

    return {
        "sales_profit": sum(r["profit"] for r in sales),
        "repairs_profit": sum(r["profit"] for r in repairs),
        "total_profit": sum(r["profit"] for r in REPORTS),
        "reports": REPORTS
    }

@app.delete("/analytics/clear")
async def clear_analytics():
    REPORTS.clear()
    return {"ok": True}

# =========================
# USERS ADMIN
# =========================

@app.get("/users")
async def get_users():

    result = []

    for username, user in USERS.items():
        result.append({
            "username": username,
            "role": user["role"],
            "blocked": user["blocked"],
            "created_at": user["created_at"]
        })

    return result

@app.post("/users/block")
async def block_user(data: dict):

    username = data.get("username")

    if username not in USERS:
        raise HTTPException(404, "Пользователь не найден")

    USERS[username]["blocked"] = True

    return {"ok": True}

@app.post("/users/unblock")
async def unblock_user(data: dict):

    username = data.get("username")

    if username not in USERS:
        raise HTTPException(404, "Пользователь не найден")

    USERS[username]["blocked"] = False

    return {"ok": True}

@app.delete("/users/delete")
async def delete_user(data: dict):

    username = data.get("username")

    if username not in USERS:
        raise HTTPException(404, "Пользователь не найден")

    del USERS[username]

    return {"ok": True}

# =========================
# REPORTS
# =========================

@app.get("/reports")
async def get_reports():
    return REPORTS

# =========================
# ADMIN
# =========================

@app.get("/admin")
async def admin():

    users = []

    for username, user in USERS.items():
        users.append({
            "username": username,
            "role": user["role"],
            "blocked": user["blocked"]
        })

    return {
        "users": users,
        "reports": REPORTS
    }

# =========================
# HEALTH
# =========================

@app.get("/health")
async def health():
    return {"status": "ok"}

# =========================
# IPARTS SEARCH
# =========================

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

        r = requests.get(
            url,
            headers=headers,
            timeout=10
        )

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

                await page.wait_for_timeout(4000)

                elements = await page.query_selector_all("div")

                items = []

                for el in elements:

                    text = await el.inner_text()

                    if "BYN" in text and len(text) < 200:

                        lines = text.split("\n")

                        items.append({
                            "name": lines[0][:100],
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

    return [
        {
            "name": f"{q} (нет данных)",
            "price": "—"
        }
    ]

# =========================
# RUN
# =========================

if __name__ == "__main__":

    import uvicorn

    port = int(os.getenv("PORT", 8000))

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port
    )