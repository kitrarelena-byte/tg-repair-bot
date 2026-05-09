import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from passlib.context import CryptContext

from bot import run_bot

# ---------- IPARTS ----------
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("main")

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# ---------- BOT ----------
async def safe_bot():
    try:
        await run_bot()
    except Exception as e:
        logger.exception(e)

# ---------- STORAGE ----------
USERS = {}
SESSIONS = {}
REPORTS = []
CACHE = {}

# ---------- MODELS ----------
class RegisterIn(BaseModel):
    username: str
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


class ReportIn(BaseModel):
    telegram_id: str = "web"
    type: str
    model: str
    purchase_price: float = 0
    repair_cost: float = 0
    sell_price: float = 0


# ---------- PASSWORD ----------
def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str):
    return pwd_context.verify(password, hashed)

# ---------- APP ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(safe_bot())
    yield

app = FastAPI(lifespan=lifespan)

# ---------- STATIC ----------
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

# ---------- REGISTER ----------
@app.post("/register")
async def register(data: RegisterIn):

    username = data.username.strip().lower()

    if len(username) < 3:
        raise HTTPException(
            400,
            "Слишком короткий логин"
        )

    if len(data.password) < 5:
        raise HTTPException(
            400,
            "Слишком короткий пароль"
        )

    if username in USERS:
        raise HTTPException(
            400,
            "Пользователь уже существует"
        )

    USERS[username] = {
        "id": str(uuid4()),
        "username": username,
        "password": hash_password(data.password),
        "role": "admin" if len(USERS) == 0 else "user",
        "created_at": datetime.utcnow().isoformat()
    }

    return {
        "ok": True,
        "username": username
    }

# ---------- LOGIN ----------
@app.post("/login")
async def login(data: LoginIn):

    username = data.username.strip().lower()

    user = USERS.get(username)

    if not user:
        raise HTTPException(
            401,
            "Пользователь не найден"
        )

    if not verify_password(
        data.password,
        user["password"]
    ):
        raise HTTPException(
            401,
            "Неверный пароль"
        )

    token = str(uuid4())

    SESSIONS[token] = username

    return {
        "ok": True,
        "token": token,
        "username": username,
        "role": user["role"]
    }

# ---------- REPORT ----------
@app.post("/report")
async def create_report(data: ReportIn):

    if data.type == "sale":

        profit = (
            data.sell_price
            - data.purchase_price
            - data.repair_cost
        )

    elif data.type == "repair":

        # ремонт = расход
        profit = -abs(data.purchase_price)

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

# ---------- ANALYTICS ----------
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
        "sales_count": len(sales),
        "repairs_count": len(repairs),

        "sales_profit":
            sum(r["profit"] for r in sales),

        "repairs_profit":
            sum(r["profit"] for r in repairs),

        "total_profit":
            sum(r["profit"] for r in REPORTS)
    }

# ---------- CLEAR ANALYTICS ----------
@app.delete("/analytics/clear")
async def clear_analytics():

    REPORTS.clear()

    return {
        "ok": True
    }

# ---------- HISTORY ----------
@app.get("/analytics/history")
async def history():

    repairs = []
    sales = []

    for r in REPORTS:

        item = {
            "id": r["id"],
            "model": r["model"],
            "profit": r["profit"],
            "created_at": r["created_at"]
        }

        if r["type"] == "repair":
            repairs.append(item)

        elif r["type"] == "sale":
            sales.append(item)

    return {
        "repairs": repairs,
        "sales": sales
    }

# ---------- REPORTS ----------
@app.get("/reports")
async def get_reports():
    return REPORTS

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
    return {
        "status": "ok"
    }

# ---------- IPARTS ----------
@app.get("/parts/search")
async def search_parts(q: str):

    q = q.strip().lower()

    if q in CACHE:
        return CACHE[q]

    try:

        url = f"https://iparts.by/search?q={q}"

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

            if (
                "BYN" in text
                and len(text) < 200
            ):

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
            "name": f"{q} не найден",
            "price": "-"
        }
    ]

# ---------- RUN ----------
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