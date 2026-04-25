import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from bot import run_bot


# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

logger.info("🚀 MAIN FILE LOADED")


# ---------------- BOT SAFE START ----------------
async def safe_bot_start():
    try:
        logger.info("🤖 BOT STARTING...")
        await run_bot()
    except Exception as e:
        logger.exception(f"💥 BOT CRASH: {e}")


# ---------------- LIFESPAN ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔥 FASTAPI STARTUP BEGIN")

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(safe_bot_start())
        logger.info("✅ BOT TASK CREATED")
    except Exception as e:
        logger.exception(f"💥 ERROR STARTING BOT TASK: {e}")

    logger.info("🔥 FASTAPI STARTUP END")
    yield

    logger.info("🛑 FASTAPI SHUTDOWN")


# ---------------- APP ----------------
app = FastAPI(lifespan=lifespan)


# ---------------- STATIC ----------------
STATIC_DIR = "static"

if not os.path.exists(STATIC_DIR):
    logger.warning("⚠️ static folder NOT FOUND, creating...")
    os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


# ---------------- HEALTHCHECK ----------------
@app.get("/health")
async def health():
    return {"status": "ok"}


logger.info("✅ APP INITIALIZED")