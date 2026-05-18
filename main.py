# main.py

import asyncio
import hashlib
import logging
import os
import random
import re
import pandas as pd

from contextlib import asynccontextmanager
from datetime import datetime

import requests

from bs4 import BeautifulSoup

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from bot import run_bot

from playwright.async_api import async_playwright

# =========================================
# LOGGING
# =========================================

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

PLAYWRIGHT_AVAILABLE = True

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/121.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15",
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

    return hashlib.sha256(
        password.encode()
    ).hexdigest()

# =========================================
# BOT
# =========================================

async def safe_bot():

    try:
        await run_bot()

    except Exception as e:
        logger.exception(e)

# =========================================
# PLAYWRIGHT BROWSER
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
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--disable-gpu"
        ]
    )

    return BROWSER

# =========================================
# STEALTH
# =========================================

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
# PARSE PRICE
# =========================================

def normalize_price(text):

    if not text:
        return "—"

    text = text.replace("\n", " ")

    m = re.search(r'([0-9]+[.,]?[0-9]*)\s*BYN', text)

    if m:
        return m.group(0)

    return "—"

# =========================================
# PARSE CARD
# =========================================

async def parse_card(card):

    try:

        text = await card.inner_text()

        if not text:
            return None

        if "BYN" not in text:
            return None

        if len(text) > 700:
            return None

        lines = [
            x.strip()
            for x in text.split("\n")
            if x.strip()
        ]

        if len(lines) < 2:
            return None

        name = lines[0][:140]

        price = normalize_price(text)

        image = ""

        img = await card.query_selector("img")

        if img:

            src = await img.get_attribute("src")

            if src:

                if src.startswith("//"):
                    image = "https:" + src

                elif src.startswith("/"):
                    image = "https://iparts.by" + src

                else:
                    image = src

        link = ""

        a = await card.query_selector("a")

        if a:

            href = await a.get_attribute("href")

            if href:

                if href.startswith("/"):
                    link = "https://iparts.by" + href

                else:
                    link = href

        return {
            "name": name,
            "price": price,
            "image": image,
            "link": link
        }

    except:
        return None

# =========================================
# IPARTS SEARCH
# =========================================

async def search_iparts(query: str):

    browser = await get_browser()

    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        locale="ru-RU",
        viewport={
            "width": 1400,
            "height": 900
        }
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
            random.randint(3000, 5000)
        )

        selectors = [
            "article",
            ".product-layout",
            ".product-item",
            ".catalog-item",
            ".products-item",
            "div"
        ]

        cards = []

        for selector in selectors:

            try:

                cards = await page.query_selector_all(selector)

                if cards and len(cards) > 3:
                    break

            except:
                pass

        used = set()

        for card in cards:

            item = await parse_card(card)

            if not item:
                continue

            key = item["name"]

            if key in used:
                continue

            used.add(key)

            results.append(item)

            if len(results) >= 20:
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

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

@app.get("/")
async def index():

    return FileResponse(
        "static/index.html"
    )

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
# iLCD GOOGLE SHEETS
# =========================================

ILCD_CSV = "https://docs.google.com/spreadsheets/d/15C4gPRMuKMjIj8tET9AaLgNcHb_6rTRxI4ba4mK5sH8/export?format=csv"

async def search_ilcd(query: str):

    results = []

    try:

        df = pd.read_csv(ILCD_CSV)

        q = query.lower()

        for _, row in df.iterrows():

            row_text = " ".join(
                [str(x) for x in row.values]
            ).lower()

            if q in row_text:

                name = ""

                price = ""

                stock = ""

                values = [str(x) for x in row.values]

                if len(values) >= 1:
                    name = values[0]

                if len(values) >= 2:
                    price = values[1]

                if len(values) >= 3:
                    stock = values[2]

                results.append({
                    "name": name,
                    "price": str(price),
                    "stock": stock,
                    "source": "iLCD",
                    "image": "",
                    "link": "https://docs.google.com/spreadsheets/d/15C4gPRMuKMjIj8tET9AaLgNcHb_6rTRxI4ba4mK5sH8"
                })

            if len(results) >= 20:
                break

    except Exception as e:

        logger.exception(e)

    return results

# =========================================
# TOPSET
# =========================================

async def search_topset(query: str):

    results = []

    try:

        url = (
            "https://shop.topset.by/search/"
            "?text=" + query
        )

        headers = {
            "User-Agent": random.choice(USER_AGENTS)
        }

        r = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        cards = soup.find_all("div")

        used = set()

        for c in cards:

            text = c.get_text(
                " ",
                strip=True
            )

            if not text:
                continue

            if len(text) < 15:
                continue

            if len(text) > 300:
                continue

            if query.lower() not in text.lower():
                continue

            if text in used:
                continue

            used.add(text)

            price = normalize_price(text)

            img = ""

            image = c.find("img")

            if image and image.get("src"):

                src = image.get("src")

                if src.startswith("/"):
                    img = "https://shop.topset.by" + src
                else:
                    img = src

            link = ""

            a = c.find("a")

            if a and a.get("href"):

                href = a.get("href")

                if href.startswith("/"):
                    link = "https://shop.topset.by" + href
                else:
                    link = href

            results.append({
                "name": text[:180],
                "price": price,
                "stock": "Уточнять",
                "source": "Topset",
                "image": img,
                "link": link
            })

            if len(results) >= 15:
                break

    except Exception as e:

        logger.exception(e)

    return results

# =========================================
# GSMPARTS
# =========================================

async def search_gsmparts(query: str):

    results = []

    try:

        url = (
            "https://gsmparts.by/search/"
            "?q=" + query
        )

        headers = {
            "User-Agent": random.choice(USER_AGENTS)
        }

        r = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        cards = soup.find_all("div")

        used = set()

        for c in cards:

            text = c.get_text(
                " ",
                strip=True
            )

            if not text:
                continue

            if len(text) < 15:
                continue

            if len(text) > 350:
                continue

            if query.lower() not in text.lower():
                continue

            if text in used:
                continue

            used.add(text)

            price = normalize_price(text)

            img = ""

            image = c.find("img")

            if image and image.get("src"):

                src = image.get("src")

                if src.startswith("/"):
                    img = "https://gsmparts.by" + src
                else:
                    img = src

            link = ""

            a = c.find("a")

            if a and a.get("href"):

                href = a.get("href")

                if href.startswith("/"):
                    link = "https://gsmparts.by" + href
                else:
                    link = href

            results.append({
                "name": text[:180],
                "price": price,
                "stock": "Уточнять",
                "source": "GSM Parts",
                "image": img,
                "link": link
            })

            if len(results) >= 15:
                break

    except Exception as e:

        logger.exception(e)

    return results

# =========================================
# MULTI SEARCH
# =========================================

@app.get("/parts/search")
async def search_parts(q: str):

    q = q.strip()

    if not q:
        return []

    cache_key = q.lower()

    if cache_key in CACHE:
        return CACHE[cache_key]

    results = []

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "ru-RU,ru;q=0.9"
    }

    # =====================================
    # iLCD
    # =====================================

    try:

        csv_url = (
            "https://docs.google.com/spreadsheets/d/"
            "15C4gPRMuKMjIj8tET9AaLgNcHb_6rTRxI4ba4mK5sH8/"
            "export?format=csv"
        )

        r = requests.get(
            csv_url,
            headers=headers,
            timeout=20
        )

        rows = r.text.splitlines()

        for row in rows:

            if q.lower() not in row.lower():
                continue

            cols = row.split(",")

            name = cols[0] if len(cols) > 0 else q
            price = cols[1] if len(cols) > 1 else "—"
            stock = cols[2] if len(cols) > 2 else "Есть"

            results.append({
                "name": name[:180],
                "price": price,
                "stock": stock,
                "source": "iLCD",
                "image": "",
                "link": "https://docs.google.com"
            })

            if len(results) >= 10:
                break

    except Exception as e:
        logger.exception(e)

    # =====================================
    # GSMPARTS
    # =====================================

    try:

        gsm_url = (
            "https://gsmparts.by/search/"
            f"?search={q}"
        )

        r = requests.get(
            gsm_url,
            headers=headers,
            timeout=20
        )

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        cards = soup.find_all("div")

        used = set()

        for card in cards:

            text = card.get_text(
                " ",
                strip=True
            )

            if not text:
                continue

            if len(text) < 20:
                continue

            if len(text) > 500:
                continue

            low = text.lower()

            if q.lower() not in low:
                continue

            if text in used:
                continue

            used.add(text)

            price = "—"

            m = re.search(
                r"([0-9]+[.,]?[0-9]*)",
                text
            )

            if m:
                price = m.group(1) + " BYN"

            results.append({
                "name": text[:180],
                "price": price,
                "stock": "Уточнять",
                "source": "GSM Parts",
                "image": "",
                "link": gsm_url
            })

            if len(results) >= 20:
                break

    except Exception as e:
        logger.exception(e)

    # =====================================
    # TOPSET
    # =====================================

    try:

        topset_url = (
            "https://shop.topset.by/search/"
            f"?q={q}"
        )

        r = requests.get(
            topset_url,
            headers=headers,
            timeout=20
        )

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        text = soup.get_text(
            " ",
            strip=True
        )

        blocks = text.split("BYN")

        for block in blocks:

            if q.lower() not in block.lower():
                continue

            if len(block) < 20:
                continue

            if len(block) > 250:
                continue

            price_match = re.search(
                r"([0-9]+[.,]?[0-9]*)",
                block
            )

            price = (
                price_match.group(1) + " BYN"
                if price_match
                else "—"
            )

            results.append({
                "name": block[:180],
                "price": price,
                "stock": "Есть",
                "source": "Topset",
                "image": "",
                "link": topset_url
            })

            if len(results) >= 30:
                break

    except Exception as e:
        logger.exception(e)

    # =====================================
    # CLEAN DUPLICATES
    # =====================================

    clean = []

    used = set()

    for item in results:

        key = (
            item["name"][:80].lower()
        )

        if key in used:
            continue

        used.add(key)

        clean.append(item)

    CACHE[cache_key] = clean

    return clean

# =========================================
# RUN
# =========================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.getenv("PORT", 8000)
    )

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port
    )