import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from bot import run_bot

print("🚀 MAIN STARTED")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🔥 FASTAPI STARTUP")

    # защищённый запуск бота
    loop = asyncio.get_running_loop()
    loop.create_task(safe_bot_start())

    yield

    print("🛑 SHUTDOWN")


async def safe_bot_start():
    try:
        print("🤖 BOT TASK STARTING")
        await run_bot()
    except Exception as e:
        print("💥 BOT CRASH:", e)


app = FastAPI(lifespan=lifespan)

app.mount("/", StaticFiles(directory="static", html=True), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}