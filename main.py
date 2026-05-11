# main.py

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

import requests
from bs4 import BeautifulSoup

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except:
    PLAYWRIGHT_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# =========================================
# ADMIN
# =========================================

ADMIN_USERNAME = "appletech752"

# =========================================
# STORAGE
# =========================================

USERS = {}
REPORTS = []
CACHE = {}

# =========================================
# MODELS
# =========================================

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

class UsernameIn(BaseModel):
    username: str

class DeleteUserIn(BaseModel):
    username: str

# =========================================
# HASH
# =========================================

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

# =========================================
# BOT
# =========================================

async def safe_bot():
    try:
        await run_bot()
    except Exception as e:
        logger.exception(e)

# =========================================
# APP
# =========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(safe_bot())
    yield

app = FastAPI(lifespan=lifespan)

# =========================================
# STATIC
# =========================================

if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")

# =========================================
# REGISTER
# =========================================

@app.post("/register")
async def register(data: AuthIn):

    username = data.username.strip().lower()

    if username in USERS:
        raise HTTPException(
            400,
            "Пользователь уже существует"
        )

    role = (
        "admin"
        if username == ADMIN_USERNAME
        else "user"
    )

    USERS[username] = {
        "telegram_id": data.telegram_id,
        "username": username,
        "password": hash_password(data.password),
        "role": role,
        "blocked": False,
        "created_at": datetime.utcnow().isoformat()
    }

    return {
        "username": username,
        "role": role,
        "blocked": False
    }

# =========================================
# LOGIN
# =========================================

@app.post("/login")
async def login(data: AuthIn):

    username = data.username.strip().lower()

    user = USERS.get(username)

    if not user:
        raise HTTPException(
            404,
            "Аккаунт не найден"
        )

    if user["telegram_id"] != data.telegram_id:
        raise HTTPException(
            403,
            "Этот аккаунт принадлежит другому Telegram аккаунту"
        )

    if user["blocked"]:
        raise HTTPException(
            403,
            "Вы заблокированы"
        )

    if user["password"] != hash_password(data.password):
        raise HTTPException(
            401,
            "Неверный пароль"
        )

    return {
        "username": user["username"],
        "role": user["role"],
        "blocked": user["blocked"]
    }

# =========================================
# USERS
# =========================================

@app.get("/users")
async def users():

    return [
        {
            "username": u["username"],
            "role": u["role"],
            "blocked": u["blocked"]
        }
        for u in USERS.values()
    ]

# =========================================
# BLOCK USER
# =========================================

@app.post("/admin/block")
async def block_user(data: UsernameIn):

    username = data.username.strip().lower()

    if username in USERS:
        USERS[username]["blocked"] = True

    return {"ok": True}

# =========================================
# UNBLOCK USER
# =========================================

@app.post("/admin/unblock")
async def unblock_user(data: UsernameIn):

    username = data.username.strip().lower()

    if username in USERS:
        USERS[username]["blocked"] = False

    return {"ok": True}

# =========================================
# DELETE USER
# =========================================

@app.post("/admin/delete")
async def delete_user(data: DeleteUserIn):

    username = data.username.strip().lower()

    if username in USERS:
        del USERS[username]

    return {"ok": True}

# =========================================
# REPORT
# =========================================

@app.post("/report")
async def create_report(data: ReportIn):

    current_user = None

    for u in USERS.values():

        if u["telegram_id"] == data.telegram_id:
            current_user = u
            break

    if not current_user:

        raise HTTPException(
            401,
            "Требуется вход в аккаунт"
        )

    if current_user["blocked"]:

        raise HTTPException(
            403,
            "Вы заблокированы"
        )

    if data.type == "sale":

        profit = (
            data.sell_price
            - data.purchase_price
            - data.repair_cost
        )

    elif data.type == "repair":

        profit = (
            data.repair_cost
            - data.purchase_price
        )

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

# =========================================
# ANALYTICS
# =========================================

@app.get("/analytics")
async def analytics():

    sales = [
        r for r in REPORTS
        if r["type"] == "sale"
    ]

    repairs = [
        r for r in REPORTS
        if r["type"] == "repair"
    ]

    return {
        "sales_profit": sum(r["profit"] for r in sales),
        "repairs_profit": sum(r["profit"] for r in repairs),
        "total_profit": sum(r["profit"] for r in REPORTS)
    }

# =========================================
# CLEAR REPORTS
# =========================================

@app.post("/clear-reports")
async def clear_reports():

    REPORTS.clear()

    return {"ok": True}

# =========================================
# REPORTS
# =========================================

@app.get("/reports")
async def get_reports():
    return REPORTS

# =========================================
# ADMIN
# =========================================

@app.get("/admin")
async def admin():

    return {
        "users": USERS,
        "reports": REPORTS
    }

# =========================================
# HEALTH
# =========================================

@app.get("/health")
async def health():
    return {"status": "ok"}

# =========================================
# IPARTS SEARCH
# =========================================

@app.get("/parts/search")
async def search_parts(q: str):

    q = q.strip().lower()

    if q in CACHE:
        return CACHE[q]

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
                    "name": text[:120],
                    "price": text.split()[-1]
                })

            if len(items) >= 10:
                break

        if items:
            CACHE[q] = items
            return items

    except Exception as e:
        logger.exception(e)

    # PLAYWRIGHT FALLBACK

    if PLAYWRIGHT_AVAILABLE:

        try:

            async with async_playwright() as p:

                browser = await p.chromium.launch(
                    headless=True
                )

                page = await browser.new_page()

                await page.goto(
                    f"https://iparts.by/search/?q={q}",
                    timeout=60000
                )

                await page.wait_for_timeout(3000)

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

    return [
        {
            "name": f"{q} (нет данных)",
            "price": "—"
        }
    ]

# =========================================
# RUN
# =========================================

if __name__ == "__main__":

    import uvicorn

    port = int(os.getenv("PORT", 8000))

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port
    )