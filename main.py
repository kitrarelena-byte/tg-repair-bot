import asyncio
import logging
import os
import sqlite3
import hashlib

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
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

DB = "crm.db"

# =========================
# DATABASE
# =========================

conn = sqlite3.connect(DB, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id TEXT UNIQUE,
    username TEXT,
    password TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id TEXT,
    type TEXT,
    model TEXT,
    purchase_price REAL,
    repair_cost REAL,
    sell_price REAL,
    profit REAL,
    created_at TEXT
)
""")

conn.commit()

CACHE = {}

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
# HASH
# =========================

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

# =========================
# REGISTER
# =========================

@app.post("/register")
async def register(data: dict):

    telegram_id = str(data.get("telegram_id"))
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return {"ok": False, "error": "missing fields"}

    existing = cursor.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (telegram_id,)
    ).fetchone()

    if existing:
        return {"ok": False, "error": "already exists"}

    cursor.execute("""
    INSERT INTO users (
        telegram_id,
        username,
        password,
        created_at
    )
    VALUES (?, ?, ?, ?)
    """, (
        telegram_id,
        username,
        hash_password(password),
        datetime.utcnow().isoformat()
    ))

    conn.commit()

    return {"ok": True}

# =========================
# LOGIN
# =========================

@app.post("/login")
async def login(data: dict):

    telegram_id = str(data.get("telegram_id"))
    username = data.get("username")
    password = data.get("password")

    user = cursor.execute("""
    SELECT * FROM users
    WHERE telegram_id=? AND username=? AND password=?
    """, (
        telegram_id,
        username,
        hash_password(password)
    )).fetchone()

    if not user:
        return {
            "ok": False,
            "error": "invalid login"
        }

    return {
        "ok": True,
        "username": username
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
        profit = (
            data.repair_cost
            - data.purchase_price
        )

    else:
        profit = 0

    cursor.execute("""
    INSERT INTO reports (
        telegram_id,
        type,
        model,
        purchase_price,
        repair_cost,
        sell_price,
        profit,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.telegram_id,
        data.type,
        data.model,
        data.purchase_price,
        data.repair_cost,
        data.sell_price,
        profit,
        datetime.utcnow().isoformat()
    ))

    conn.commit()

    return {
        "ok": True,
        "profit": profit
    }

# =========================
# ANALYTICS
# =========================

@app.get("/analytics")
async def analytics():

    rows = cursor.execute("""
    SELECT type, profit FROM reports
    """).fetchall()

    sales_profit = 0
    repairs_profit = 0

    for r in rows:

        if r[0] == "sale":
            sales_profit += r[1]

        if r[0] == "repair":
            repairs_profit += r[1]

    return {
        "sales_profit": sales_profit,
        "repairs_profit": repairs_profit,
        "total_profit": sales_profit + repairs_profit
    }

# =========================
# REPORTS
# =========================

@app.get("/reports")
async def reports():

    rows = cursor.execute("""
    SELECT
        id,
        telegram_id,
        type,
        model,
        profit,
        created_at
    FROM reports
    ORDER BY id DESC
    """).fetchall()

    result = []

    for r in rows:
        result.append({
            "id": r[0],
            "telegram_id": r[1],
            "type": r[2],
            "model": r[3],
            "profit": r[4],
            "created_at": r[5]
        })

    return result

# =========================
# CLEAR ANALYTICS
# =========================

@app.post("/analytics/clear")
async def clear_analytics():

    cursor.execute("DELETE FROM reports")
    conn.commit()

    return {"ok": True}

# =========================
# ADMIN
# =========================

@app.get("/admin")
async def admin():

    users = cursor.execute("""
    SELECT telegram_id, username
    FROM users
    """).fetchall()

    reports = cursor.execute("""
    SELECT COUNT(*)
    FROM reports
    """).fetchone()[0]

    return {
        "users": users,
        "reports": reports
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
        logger.exception(e)

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