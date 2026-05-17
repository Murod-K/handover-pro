import asyncio
import logging
import os
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from bot.handlers import start, shifts, photos, voice
from bot.handlers.notify import scheduler_task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://handover-pro-bot.onrender.com/webhook")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.include_router(start.router)
dp.include_router(shifts.router)
dp.include_router(photos.router)
dp.include_router(voice.router)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook set to {WEBHOOK_URL}")
    task = asyncio.create_task(scheduler_task(bot))
    yield
    task.cancel()
    await bot.delete_webhook()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/webhook")
async def webhook(request: Request):
    from aiogram.types import Update
    body = await request.json()
    update = Update(**body)
    await dp.feed_update(bot=bot, update=update)
    return {"ok": True}

@app.get("/app")
async def mini_app():
    return FileResponse("mini_app/index.html")

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
