# main.py

import asyncio
import logging
import os
import hashlib
import random

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bot import run_bot

import requests
from bs4 import BeautifulSoup

from playwright.async_api import async_playwright

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
# PLAYWRIGHT
# =========================================

BROWSER = None

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (X11; Linux x86_64)"
]

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
# PLAYWRIGHT
# =========================================

async def get_browser():

    global BROWSER

    if BROWSER:
        return BROWSER

    playwright = await async_playwright().start()

    BROWSER = await playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage"
        ]
    )

    return BROWSER

async def stealth(page):

    await page.add_init_script("""
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

window.chrome = {
    runtime: {}
};

Object.defineProperty(navigator, 'plugins', {
    get: () => [1,2,3]
});

Object.defineProperty(navigator, 'languages', {
    get: () => ['ru-RU', 'ru']
});
    """)

# =========================================
# IPARTS PARSER
# =========================================

async def search_iparts(query: str):

    browser = await get_browser()

    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        locale="ru-RU",
        viewport={"width": 1366, "height": 768}
    )

    page = await context.new_page()

    await stealth(page)

    results = []

    try:

        await page.goto(
            f"https://iparts.by/search/?q={query}",
            wait_until="domcontentloaded",
            timeout=90000
        )

        await page.wait_for_timeout(
            random.randint(2500, 5000)
        )

        cards = await page.query_selector_all("article")

        if not cards:
            cards = await page.query_selector_all("div")

        for card in cards:

            try:

                text = await card.inner_text()

                if not text:
                    continue

                if "BYN" not in text:
                    continue

                if len(text) > 500:
                    continue

                lines = [
                    x.strip()
                    for x in text.split("\n")
                    if x.strip()
                ]

                if len(lines) < 2:
                    continue

                name = lines[0][:120]

                price = "Не указана"

                for line in lines:
                    if "BYN" in line:
                        price = line
                        break

                image = ""

                img_el = await card.query_selector("img")

                if img_el:

                    src = await img_el.get_attribute("src")

                    if src:
                        image = src

                link = ""

                link_el = await card.query_selector("a")

                if link_el:

                    href = await link_el.get_attribute("href")

                    if href:

                        if href.startswith("/"):
                            link = "https://iparts.by" + href
                        else:
                            link = href

                results.append({
                    "name": name,
                    "price": price,
                    "image": image,
                    "link": link
                })

            except:
                pass

            if len(results) >= 15:
                break

    except Exception as e:
        logger.exception(e)

    finally:
        await context.close()

    return results

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
            status_code=400,
            detail="Пользователь уже существует"
        )

    role = "admin" if username == ADMIN_USERNAME else "user"

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
            status_code=404,
            detail="Аккаунт не найден"
        )

    if user["telegram_id"] != data.telegram_id:

        raise HTTPException(
            status_code=403,
            detail="Этот аккаунт принадлежит другому Telegram аккаунту"
        )

    if user["blocked"]:

        raise HTTPException(
            status_code=403,
            detail="Вы заблокированы"
        )

    if user["password"] != hash_password(data.password):

        raise HTTPException(
            status_code=401,
            detail="Неверный пароль"
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
            "blocked": u["blocked"],
            "created_at": u["created_at"]
        }
        for u in USERS.values()
    ]

# =========================================
# BLOCK
# =========================================

@app.post("/admin/block")
async def block_user(data: UsernameIn):

    username = data.username.lower()

    if username in USERS:
        USERS[username]["blocked"] = True

    return {"ok": True}

# =========================================
# UNBLOCK
# =========================================

@app.post("/admin/unblock")
async def unblock_user(data: UsernameIn):

    username = data.username.lower()

    if username in USERS:
        USERS[username]["blocked"] = False

    return {"ok": True}

# =========================================
# DELETE
# =========================================

@app.post("/admin/delete")
async def delete_user(data: UsernameIn):

    username = data.username.lower()

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

    if current_user and current_user.get("blocked"):

        raise HTTPException(
            status_code=403,
            detail="Вы заблокированы"
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

        data = await search_iparts(q)

        if data:

            CACHE[q] = data

            return data

    except Exception as e:
        logger.exception(e)

    return [
        {
            "name": f"{q} (нет данных)",
            "price": "—",
            "image": "",
            "link": ""
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