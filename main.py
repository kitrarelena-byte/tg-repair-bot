import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

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

# ---------- LIFESPAN ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔥 STARTUP")

    loop = asyncio.get_event_loop()
    loop.create_task(safe_bot())

    yield

    logger.info("🛑 SHUTDOWN")

# ---------- APP ----------
app = FastAPI(lifespan=lifespan)

# ---------- STATIC ----------
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/", StaticFiles(directory="static", html=True), name="static")

# ---------- HEALTH ----------
@app.get("/health")
async def health():
    return {"status": "ok"}

# ---------- LOCAL RUN ----------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))

    uvicorn.run("main:app", host="0.0.0.0", port=port)