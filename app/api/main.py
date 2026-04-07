# app/api/main.py

import sys
import os
import uuid
import time
import logging
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.synthesis.response_generator import ResponseGenerator
from app.api.models import ChatRequest, ChatResponse
from app.bot.handlers import dp, bot, medical_assistant

load_dotenv = __import__("dotenv").load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global medical_assistant
    
    logger.info("🚀 Starting Medical Assistant with Webhook...")

    # 1. Initialize Medical Assistant
    ResponseGenerator.initialize()
    medical_assistant = ResponseGenerator()

    # 2. Smart Webhook Management
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        logger.warning("⚠️ WEBHOOK_URL not set in .env — Running without webhook (polling mode)")
    else:
        try:
            # Check current webhook
            webhook_info = await bot.get_webhook_info()
            
            if webhook_info.url == webhook_url:
                logger.info(f"✅ Webhook already set correctly")
            else:
                # Set or update webhook
                await bot.set_webhook(
                    url=webhook_url,
                    drop_pending_updates=True,   # Clean old updates
                    allowed_updates=["message", "callback_query"]
                )
                logger.info(f"🔄 Webhook successfully set/updated")
        except Exception as e:
            logger.error(f"❌ Failed to set webhook: {e}")

    yield  # Application runs here

    logger.info("🛑 Medical Assistant shutdown complete.")


app = FastAPI(lifespan=lifespan, title="Medical Assistant API + Webhook")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.model_validate(data) 
        await dp.feed_update(bot, update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return {"status": "error"}


# Health check
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Medical Assistant (Webhook Mode)"
    }


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    structured = medical_assistant.generate_structured(request.query)
    return {
        "query_id": structured["query_id"],
        "session_id": request.session_id or str(uuid.uuid4())[:8],
        "condition_detected": structured["condition"],
        "urgency_level": structured["urgency_level"],
        "summary": structured["summary"],
        "urgency_friendly": structured["urgency_friendly"],
        "available_sections": structured["available_sections"],
        "sections": structured["sections"],
        "latency_ms": structured["latency_ms"]
    }
    

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=8080,
        log_level="info",
    )