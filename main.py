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

# =========================
# ADMIN
# =========================

ADMIN_USERNAME = "appletech752"

# =========================
# BOT
# =========================

async def safe_bot():
    try:
        await run_bot()
    except Exception as e:
        logger.exception(e)

# =========================
# STORAGE
# =========================

USERS = {}
REPORTS = []
CACHE = {}

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
# HELPERS
# =========================

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_by_username(username):
    for tg_id, user in USERS.items():
        if user["username"] == username:
            return tg_id, user
    return None, None

# =========================
# REGISTER
# =========================

@app.post("/register")
async def register(data: dict):

    tg_id = str(data.get("telegram_id"))
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        raise HTTPException(status_code=400, detail="Заполни поля")

    # уже есть аккаунт на этом tg
    if tg_id in USERS:
        raise HTTPException(status_code=400, detail="Аккаунт уже создан")

    # логин занят
    _, existing = get_user_by_username(username)

    if existing:
        raise HTTPException(status_code=400, detail="Логин занят")

    USERS[tg_id] = {
        "telegram_id": tg_id,
        "username": username,
        "password": hash_password(password),
        "role": "admin" if username == ADMIN_USERNAME else "user",
        "blocked": False,
        "created_at": datetime.utcnow().isoformat()
    }

    return {
        "ok": True,
        "user": USERS[tg_id]
    }

# =========================
# LOGIN
# =========================

@app.post("/login")
async def login(data: dict):

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    tg_id, user = get_user_by_username(username)

    if not user:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")

    if user["blocked"]:
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")

    if user["password"] != hash_password(password):
        raise HTTPException(status_code=401, detail="Неверный пароль")

    return {
        "ok": True,
        "user": {
            "telegram_id": user["telegram_id"],
            "username": user["username"],
            "role": user["role"]
        }
    }

# =========================
# BLOCK USER
# =========================

@app.post("/admin/block")
async def block_user(data: dict):

    admin_username = data.get("admin_username")
    target = data.get("target")

    _, admin = get_user_by_username(admin_username)

    if not admin or admin["role"] != "admin":
        raise HTTPException(status_code=403, detail="Нет доступа")

    tg_id, user = get_user_by_username(target)

    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    user["blocked"] = True

    return {"ok": True}

# =========================
# UNBLOCK USER
# =========================

@app.post("/admin/unblock")
async def unblock_user(data: dict):

    admin_username = data.get("admin_username")
    target = data.get("target")

    _, admin = get_user_by_username(admin_username)

    if not admin or admin["role"] != "admin":
        raise HTTPException(status_code=403, detail="Нет доступа")

    tg_id, user = get_user_by_username(target)

    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    user["blocked"] = False

    return {"ok": True}

# =========================
# DELETE USER
# =========================

@app.post("/admin/delete")
async def delete_user(data: dict):

    admin_username = data.get("admin_username")
    target = data.get("target")

    _, admin = get_user_by_username(admin_username)

    if not admin or admin["role"] != "admin":
        raise HTTPException(status_code=403, detail="Нет доступа")

    tg_id, user = get_user_by_username(target)

    if not user:
        raise HTTPException(status_code=404, detail="Не найден")

    del USERS[tg_id]

    return {"ok": True}

# =========================
# REPORT
# =========================

@app.post("/report")
async def create_report(data: ReportIn):

    user = USERS.get(str(data.telegram_id))

    if not user:
        raise HTTPException(status_code=401, detail="Авторизуйся")

    if user["blocked"]:
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")

    if data.type == "sale":
        profit = data.sell_price - data.purchase_price - data.repair_cost

    elif data.type == "repair":
        profit = data.repair_cost - data.purchase_price

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
# ANALYTICS
# =========================

@app.get("/analytics")
async def analytics():

    sales = [r for r in REPORTS if r["type"] == "sale"]
    repairs = [r for r in REPORTS if r["type"] == "repair"]

    return {
        "sales_profit": sum(r["profit"] for r in sales),
        "repairs_profit": sum(r["profit"] for r in repairs),
        "total_profit": sum(r["profit"] for r in REPORTS)
    }

# =========================
# CLEAR ANALYTICS
# =========================

@app.post("/analytics/clear")
async def clear_analytics():
    REPORTS.clear()
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

    safe_users = {}

    for tg_id, u in USERS.items():
        safe_users[tg_id] = {
            "username": u["username"],
            "role": u["role"],
            "blocked": u["blocked"]
        }

    return {
        "users": safe_users,
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