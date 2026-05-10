import asyncio
import logging
import os

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from pydantic import BaseModel

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from bot import run_bot

# ---------- IPARTS ----------
import requests
from bs4 import BeautifulSoup

# ---------- PLAYWRIGHT ----------
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except:
    PLAYWRIGHT_AVAILABLE = False

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("main")

# =========================
ADMIN
# =========================

ADMIN_USERNAME = "appletech752"

# =========================
BOT
# =========================

async def safe_bot():
    try:
        await run_bot()
    except Exception as e:
        logger.exception(e)

# =========================
STORAGE
# =========================

USERS = {}

# username -> user
USERNAMES = {}

REPORTS = []

CACHE = {}

# =========================
MODELS
# =========================

class ReportIn(BaseModel):
    telegram_id: str
    type: str
    model: str
    purchase_price: float = 0
    repair_cost: float = 0
    sell_price: float = 0

# =========================
APP
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):

    asyncio.create_task(safe_bot())

    yield

app = FastAPI(lifespan=lifespan)

# =========================
STATIC
# =========================

if not os.path.exists("static"):
    os.makedirs("static")

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

@app.get("/")
async def index():
    return FileResponse("static/index.html")

# =========================
REGISTER
# =========================

@app.post("/register")
async def register(data: dict):

    telegram_id = str(data.get("telegram_id"))

    username = data.get("username", "").strip()

    password = data.get("password", "").strip()

    if not username or not password:
        raise HTTPException(
            400,
            "Заполни логин и пароль"
        )

    if username in USERNAMES:
        raise HTTPException(
            400,
            "Аккаунт уже существует"
        )

    if telegram_id in USERS:
        raise HTTPException(
            400,
            "На этом Telegram уже есть аккаунт"
        )

    role = (
        "admin"
        if username == ADMIN_USERNAME
        else "user"
    )

    user = {
        "telegram_id": telegram_id,
        "username": username,
        "password": generate_password_hash(password),
        "role": role,
        "blocked": False,
        "created_at": datetime.utcnow().isoformat()
    }

    USERS[telegram_id] = user

    USERNAMES[username] = user

    return {
        "ok": True,
        "user": {
            "telegram_id": telegram_id,
            "username": username,
            "role": role
        }
    }

# =========================
LOGIN
# =========================

@app.post("/login")
async def login(data: dict):

    username = data.get("username", "").strip()

    password = data.get("password", "").strip()

    user = USERNAMES.get(username)

    if not user:
        raise HTTPException(
            404,
            "Аккаунт не найден"
        )

    if user.get("blocked"):
        raise HTTPException(
            403,
            "Аккаунт заблокирован"
        )

    if not check_password_hash(
        user["password"],
        password
    ):
        raise HTTPException(
            401,
            "Неверный пароль"
        )

    return {
        "ok": True,
        "user": {
            "telegram_id": user["telegram_id"],
            "username": user["username"],
            "role": user["role"]
        }
    }

# =========================
REPORT
# =========================

@app.post("/report")
async def create_report(data: ReportIn):

    user = USERS.get(str(data.telegram_id))

    if not user:
        raise HTTPException(
            401,
            "Пользователь не найден"
        )

    if user.get("blocked"):
        raise HTTPException(
            403,
            "Аккаунт заблокирован"
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
        "username": user["username"],
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
ANALYTICS
# =========================

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
        "sales_profit":
            sum(r["profit"] for r in sales),

        "repairs_profit":
            sum(r["profit"] for r in repairs),

        "total_profit":
            sum(r["profit"] for r in REPORTS)
    }

@app.post("/analytics/clear")
async def clear_analytics():

    REPORTS.clear()

    return {"ok": True}

# =========================
REPORTS
# =========================

@app.get("/reports")
async def get_reports():
    return REPORTS

# =========================
ADMIN
# =========================

@app.get("/admin")
async def admin():

    return {
        "users": USERS,
        "reports": REPORTS
    }

@app.post("/admin/block")
async def block_user(data: dict):

    admin_username = data.get("admin_username")

    target = data.get("target")

    admin_user = USERNAMES.get(admin_username)

    if not admin_user:
        raise HTTPException(403, "Нет доступа")

    if admin_user["role"] != "admin":
        raise HTTPException(403, "Нет доступа")

    user = USERNAMES.get(target)

    if not user:
        raise HTTPException(404, "Не найден")

    user["blocked"] = True

    return {"ok": True}

@app.post("/admin/unblock")
async def unblock_user(data: dict):

    admin_username = data.get("admin_username")

    target = data.get("target")

    admin_user = USERNAMES.get(admin_username)

    if not admin_user:
        raise HTTPException(403, "Нет доступа")

    if admin_user["role"] != "admin":
        raise HTTPException(403, "Нет доступа")

    user = USERNAMES.get(target)

    if not user:
        raise HTTPException(404, "Не найден")

    user["blocked"] = False

    return {"ok": True}

@app.post("/admin/delete")
async def delete_user(data: dict):

    admin_username = data.get("admin_username")

    target = data.get("target")

    admin_user = USERNAMES.get(admin_username)

    if not admin_user:
        raise HTTPException(403, "Нет доступа")

    if admin_user["role"] != "admin":
        raise HTTPException(403, "Нет доступа")

    user = USERNAMES.get(target)

    if not user:
        raise HTTPException(404, "Не найден")

    telegram_id = user["telegram_id"]

    USERNAMES.pop(target, None)

    USERS.pop(telegram_id, None)

    return {"ok": True}

# =========================
HEALTH
# =========================

@app.get("/health")
async def health():
    return {"status": "ok"}

# =========================
IPARTS SEARCH
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

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        items = []

        for el in soup.find_all("div"):

            text = el.get_text(
                " ",
                strip=True
            )

            if "BYN" in text and len(text) < 200:

                items.append({
                    "name": text[:80],
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

                html = await page.content()

                await browser.close()

                soup = BeautifulSoup(
                    html,
                    "html.parser"
                )

                items = []

                for el in soup.find_all("div"):

                    text = el.get_text(
                        " ",
                        strip=True
                    )

                    if "BYN" in text and len(text) < 200:

                        items.append({
                            "name": text[:80],
                            "price": text.split()[-1]
                        })

                    if len(items) >= 10:
                        break

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
RUN
# =========================

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