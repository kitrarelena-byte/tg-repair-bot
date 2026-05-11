import asyncio
import logging
import os
import hashlib
import base64
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
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

ADMIN_USERNAME = "appletech752"

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
    telegram_username: str = ""

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

if not os.path.exists("static/avatars"):
    os.makedirs("static/avatars")

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
        raise HTTPException(400, "Пользователь уже существует")

    role = "admin" if username == ADMIN_USERNAME else "user"

    USERS[username] = {
        "telegram_id": data.telegram_id,
        "telegram_username": data.telegram_username,
        "username": username,
        "password": hash_password(data.password),
        "role": role,
        "blocked": False,
        "avatar": "",
        "created_at": datetime.utcnow().isoformat()
    }

    return {
        "username": username,
        "telegram_username": data.telegram_username,
        "role": role,
        "blocked": False,
        "avatar": ""
    }

# =========================================
# LOGIN
# =========================================

@app.post("/login")
async def login(data: AuthIn):

    username = data.username.strip().lower()

    user = USERS.get(username)

    if not user:
        raise HTTPException(404, "Аккаунт не найден")

    if user["telegram_id"] != data.telegram_id:
        raise HTTPException(
            403,
            "Этот аккаунт привязан к другому Telegram аккаунту"
        )

    if user["blocked"]:
        raise HTTPException(403, "Вы заблокированы")

    if user["password"] != hash_password(data.password):
        raise HTTPException(401, "Неверный пароль")

    return {
        "username": user["username"],
        "telegram_username": user.get("telegram_username", ""),
        "role": user["role"],
        "blocked": user["blocked"],
        "avatar": user.get("avatar", "")
    }

# =========================================
# PROFILE
# =========================================

@app.get("/profile/{telegram_id}")
async def get_profile(telegram_id: str):

    for user in USERS.values():
        if user["telegram_id"] == telegram_id:

            return {
                "username": user["username"],
                "telegram_username": user.get("telegram_username", ""),
                "role": user["role"],
                "blocked": user["blocked"],
                "avatar": user.get("avatar", "")
            }

    raise HTTPException(404, "Пользователь не найден")

# =========================================
# AVATAR
# =========================================

@app.post("/upload-avatar")
async def upload_avatar(
    telegram_id: str = Form(...),
    avatar: UploadFile = File(...)
):

    try:

        allowed = [
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/jpg"
        ]

        if avatar.content_type not in allowed:
            raise HTTPException(400, "Неподдерживаемый формат")

        ext = avatar.filename.split(".")[-1]

        filename = f"{telegram_id}.{ext}"

        filepath = f"static/avatars/{filename}"

        content = await avatar.read()

        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(400, "Файл слишком большой")

        with open(filepath, "wb") as f:
            f.write(content)

        for user in USERS.values():

            if user["telegram_id"] == telegram_id:
                user["avatar"] = f"/static/avatars/{filename}"

                return {
                    "ok": True,
                    "avatar": user["avatar"]
                }

        raise HTTPException(404, "Пользователь не найден")

    except Exception as e:
        logger.exception(e)
        raise HTTPException(500, "Ошибка загрузки")

# =========================================
# USERS
# =========================================

@app.get("/users")
async def users():

    return [
        {
            "username": u["username"],
            "telegram_username": u.get("telegram_username", ""),
            "role": u["role"],
            "blocked": u["blocked"],
            "avatar": u.get("avatar", "")
        }
        for u in USERS.values()
    ]

# =========================================
# BLOCK USER
# =========================================

@app.post("/admin/block")
async def block_user(data: UsernameIn):

    username = data.username.lower()

    if username not in USERS:
        raise HTTPException(404, "Пользователь не найден")

    USERS[username]["blocked"] = True

    return {"ok": True}

# =========================================
# UNBLOCK USER
# =========================================

@app.post("/admin/unblock")
async def unblock_user(data: UsernameIn):

    username = data.username.lower()

    if username not in USERS:
        raise HTTPException(404, "Пользователь не найден")

    USERS[username]["blocked"] = False

    return {"ok": True}

# =========================================
# DELETE USER
# =========================================

@app.post("/admin/delete")
async def delete_user(data: UsernameIn):

    username = data.username.lower()

    if username not in USERS:
        raise HTTPException(404, "Пользователь не найден")

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
        raise HTTPException(401, "Авторизуйтесь")

    if current_user["blocked"]:
        raise HTTPException(403, "Вы заблокированы")

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
        "username": current_user["username"],
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