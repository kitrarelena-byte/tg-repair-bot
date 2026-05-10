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

# =========================================================
# ADMIN
# =========================================================

ADMIN_USERNAME = "AppleTech752"
ADMIN_TELEGRAM = "chickMaya"

# =========================================================
# BOT
# =========================================================

async def safe_bot():
    try:
        await run_bot()
    except Exception as e:
        logger.exception(e)

# =========================================================
# STORAGE
# =========================================================

USERS = {}
REPORTS = []
CACHE = {}

# =========================================================
# MODELS
# =========================================================

class ReportIn(BaseModel):
    telegram_id: str
    type: str
    model: str
    purchase_price: float = 0
    repair_cost: float = 0
    sell_price: float = 0

# =========================================================
# APP
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(safe_bot())
    yield

app = FastAPI(lifespan=lifespan)

# =========================================================
# STATIC
# =========================================================

if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return FileResponse("static/index.html")

# =========================================================
# HELPERS
# =========================================================

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

def find_user_by_username(username):
    for user_id, user in USERS.items():
        if user["username"].lower() == username.lower():
            return user_id, user
    return None, None

# =========================================================
# REGISTER
# =========================================================

@app.post("/register")
async def register(data: dict):

    tg_id = str(data.get("telegram_id"))
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        raise HTTPException(status_code=400, detail="Введите логин и пароль")

    existing_id, existing_user = find_user_by_username(username)

    if existing_user:
        raise HTTPException(status_code=400, detail="Логин уже занят")

    role = "user"

    if username == ADMIN_USERNAME:
        role = "admin"

    USERS[tg_id] = {
        "telegram_id": tg_id,
        "username": username,
        "password": hash_password(password),
        "role": role,
        "blocked": False,
        "created_at": datetime.utcnow().isoformat()
    }

    return {
        "ok": True,
        "username": username,
        "role": role
    }

# =========================================================
# LOGIN
# =========================================================

@app.post("/login")
async def login(data: dict):

    tg_id = str(data.get("telegram_id"))
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    existing_id, user = find_user_by_username(username)

    if not user:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")

    if user["password"] != hash_password(password):
        raise HTTPException(status_code=401, detail="Неверный пароль")

    if user.get("blocked"):
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")

    # привязка нового telegram аккаунта
    USERS[tg_id] = user

    return {
        "ok": True,
        "username": user["username"],
        "role": user["role"]
    }

# =========================================================
# USERS
# =========================================================

@app.get("/users")
async def get_users():

    result = []

    for uid, u in USERS.items():
        result.append({
            "telegram_id": uid,
            "username": u["username"],
            "role": u["role"],
            "blocked": u.get("blocked", False)
        })

    return result

# =========================================================
# BLOCK USER
# =========================================================

@app.post("/admin/block")
async def block_user(data: dict):

    username = data.get("username")

    uid, user = find_user_by_username(username)

    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    user["blocked"] = True

    return {"ok": True}

# =========================================================
# UNBLOCK USER
# =========================================================

@app.post("/admin/unblock")
async def unblock_user(data: dict):

    username = data.get("username")

    uid, user = find_user_by_username(username)

    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    user["blocked"] = False

    return {"ok": True}

# =========================================================
# REPORT
# =========================================================

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

# =========================================================
# ANALYTICS
# =========================================================

@app.get("/analytics")
async def analytics():

    sales = [r for r in REPORTS if r["type"] == "sale"]
    repairs = [r for r in REPORTS if r["type"] == "repair"]

    return {
        "sales_profit": sum(r["profit"] for r in sales),
        "repairs_profit": sum(r["profit"] for r in repairs),
        "total_profit": sum(r["profit"] for r in REPORTS)
    }

# =========================================================
# REPORTS
# =========================================================

@app.get("/reports")
async def get_reports():
    return REPORTS

# =========================================================
# CLEAR REPORTS
# =========================================================

@app.post("/clear-reports")
async def clear_reports():
    REPORTS.clear()
    return {"ok": True}

# =========================================================
# ADMIN
# =========================================================

@app.get("/admin")
async def admin():
    return {
        "users": USERS,
        "reports": REPORTS
    }

# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
async def health():
    return {"status": "ok"}

# =========================================================
# IPARTS SEARCH
# =========================================================

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

            if "BYN" in text and len(text) < 150:

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
        logger.warning("requests failed")

    return [
        {"name": f"{q} (нет данных)", "price": "—"}
    ]

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    import uvicorn

    port = int(os.getenv("PORT", 8000))

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port
    )