# app/main.py

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from app.core.config import settings
from app.bot.handlers import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()
dp.include_router(router)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    current_webhook = await bot.get_webhook_info()
    target_webhook = f"{settings.WEBHOOK_URL}"

    if current_webhook.url != target_webhook:
        logger.info(f"🔄 Webhook mismatch. Updating: {current_webhook.url} -> {target_webhook}")
        await bot.set_webhook(
            url=target_webhook,
            drop_pending_updates=True,
            allowed_updates=dp.resolve_used_update_types()
        )
    else:
        logger.info(f"✅ Webhook already correctly set to: {target_webhook}")

    yield # Running

    # --- SHUTDOWN ---
    await bot.session.close()
    logger.info("🛑 Bot session closed.")

app = FastAPI(lifespan=lifespan)


@app.post("/webhook")
async def tg_webhook(request: Request):
    """
    Seamless entry point for tg updates.
    """
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"Error processing update: {e}")
    return {"ok": True}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "medical-assistant-bot"}