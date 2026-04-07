# app/api/main.py

import sys
import os
import uuid
import time
import logging
import asyncio
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

from scripts.bootstrap import bootstrap_pipeline
from src.synthesis.response_generator import ResponseGenerator
from src.utils.redis_client import redis_client
from app.api.models import ChatRequest, ChatResponse
from app.bot.handlers import dp, bot, medical_assistant

load_dotenv = __import__("dotenv").load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global medical_assistant
    
    logger.info("⚡ Fast-starting Web Server...")
    
    # Initialize Redis (usually fast)
    await redis_client.init()

    # Move HEAVY work to a background task so it doesn't block Port 8080
    async def load_ai_logic():
        global medical_assistant
        try:
            logger.info("🧠 Loading AI Models in background...")
            if os.getenv("RUN_BOOTSTRAP", "true") == "true":
                # Offload synchronous bootstrap to a thread
                await asyncio.to_thread(bootstrap_pipeline)
            
            await ResponseGenerator.initialize()
            medical_assistant = ResponseGenerator()
            logger.info("✅ AI Ready!")
        except Exception as e:
            logger.error(f"❌ Initialization Failed: {e}")

    # Start the task without 'awaiting' it
    asyncio.create_task(load_ai_logic())

    # Webhook setup (do it quickly)
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        try:
            await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
            logger.info("🔄 Webhook set")
        except Exception as e:
            logger.error(f"Webhook error: {e}")

    yield 
    logger.info("🛑 Shutting down...")
    await redis_client.close()

    


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
@app.get("/")
@app.get("/health")
async def health_check():
    # If medical_assistant isn't ready, we are "starting" but the port is open
    is_ready = medical_assistant is not None
    return {
        "status": "healthy" if is_ready else "initializing",
        "service": "Medical Assistant",
        "ready": is_ready
    }


# @app.post("/chat", response_model=ChatResponse)
# async def chat_endpoint(request: ChatRequest):
#     structured = await asyncio.to_thread(
#         medical_assistant.generate_structured,
#         request.query
#     )
#     return {
#         "query_id": structured["query_id"],
#         "session_id": request.session_id or str(uuid.uuid4())[:8],
#         "condition_detected": structured["condition"],
#         "urgency_level": structured["urgency_level"],
#         "summary": structured["summary"],
#         "urgency_friendly": structured["urgency_friendly"],
#         "available_sections": structured["available_sections"],
#         "sections": structured["sections"],
#         "latency_ms": structured["latency_ms"]
#     }
    

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=8080,
        log_level="info",
    )