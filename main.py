import asyncio

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db import Base, engine
from services import add_report, add_part
from bot import run_bot
print("MAIN STARTED")
# -------------------
# APP INIT
# -------------------
app = FastAPI()

# создаём таблицы
Base.metadata.create_all(bind=engine)

# подключаем mini app (frontend)
app.mount("/", StaticFiles(directory="static", html=True), name="static")


# -------------------
# DATA MODELS (API)
# -------------------
class ReportIn(BaseModel):
    model: str
    repair_price: float
    sell_price: float


class PartIn(BaseModel):
    name: str
    price: float


# -------------------
# API ROUTES
# -------------------
@app.post("/report")
def create_report(r: ReportIn):
    add_report(r.model, r.repair_price, r.sell_price)
    return {"ok": True}


@app.post("/part")
def create_part(p: PartIn):
    add_part(p.name, p.price)
    return {"ok": True}


# -------------------
# STARTUP EVENT
# -------------------
@app.on_event("startup")
async def startup():
    print("🔥 FASTAPI STARTED")
    import asyncio
    asyncio.create_task(run_bot())


# -------------------
# HEALTHCHECK
# -------------------
@app.get("/health")
def health():
    return {"status": "ok"}