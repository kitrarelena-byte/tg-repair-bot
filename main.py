import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, select
from sqlalchemy.orm import declarative_base, sessionmaker

from bot import run_bot

# ---------- LOG ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("🚀 MAIN STARTED")

# ---------- BOT SAFE START ----------
async def safe_bot():
    try:
        logger.info("🤖 BOT START...")
        await run_bot()
    except Exception as e:
        logger.exception(f"BOT ERROR: {e}")

# ---------- DB ----------
DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()

# ---------- MODELS ----------
class User(Base):
    tablename = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True)
    role = Column(String, default="user")

class Report(Base):
    tablename = "reports"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String)

    type = Column(String)
    model = Column(String)

    purchase_price = Column(Float)
    repair_cost = Column(Float)
    sell_price = Column(Float)
    profit = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# ---------- FASTAPI ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔥 STARTUP")
    asyncio.create_task(safe_bot())
    yield
    logger.info("🛑 SHUTDOWN")

app = FastAPI(lifespan=lifespan)

# ---------- STATIC ----------
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/", StaticFiles(directory="static", html=True), name="static")

# ---------- SCHEMAS ----------
class ReportIn(BaseModel):
    telegram_id: str
    type: str
    model: str
    purchase_price: float = 0
    repair_cost: float = 0
    sell_price: float = 0

class RegisterIn(BaseModel):
    telegram_id: str

# ---------- REGISTER ----------
@app.post("/register")
def register(data: RegisterIn):
    db = SessionLocal()

    user = db.query(User).filter(User.telegram_id == data.telegram_id).first()

    if not user:
        role = "admin" if db.query(User).count() == 0 else "user"

        user = User(
            telegram_id=data.telegram_id,
            role=role
        )
        db.add(user)
        db.commit()

    db.close()

    return {"role": user.role}

# ---------- REPORT ----------
@app.post("/report")
def create_report(data: ReportIn):
    db = SessionLocal()

    profit = data.sell_price - data.purchase_price - data.repair_cost

    report = Report(
        telegram_id=data.telegram_id,
        type=data.type,
        model=data.model,
        purchase_price=data.purchase_price,
        repair_cost=data.repair_cost,
        sell_price=data.sell_price,
        profit=profit
    )

    db.add(report)
    db.commit()
    db.close()

    return {"ok": True, "profit": profit}

# ---------- ANALYTICS ----------
@app.get("/analytics")
def analytics():
    db = SessionLocal()

    reports = db.query(Report).all()

    total = sum(r.profit for r in reports)
    sales = len([r for r in reports if r.type == "sale"])
    repairs = len([r for r in reports if r.type == "repair"])

    db.close()

    return {
        "total_profit": total,
        "sales_count": sales,
        "repair_count": repairs
    }

# ---------- ADMIN ----------
@app.get("/admin/{telegram_id}")
def admin(telegram_id: str):
    db = SessionLocal()

    user = db.query(User).filter(User.telegram_id == telegram_id).first()

    if not user or user.role != "admin":
        return {"error": "no access"}

    users = db.query(User).all()
    reports = db.query(Report).all()

    db.close()

    return {
        "users": len(users),
        "reports": len(reports)
    }

# ---------- REPORT FILTER ----------
@app.get("/reports")
def get_reports():
    db = SessionLocal()

    reports = db.query(Report).all()

    db.close()

    return reports

# ---------- HEALTH ----------
@app.get("/health")
def health():
    return {"status": "ok"}

# ---------- RUN ----------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000))
    )