# app/api/main.py

import sys
import os
import uuid
import time
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Dict
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from aiogram.types import Update
from app.api.models import ChatRequest, ChatResponse

from src.utils.redis_client import redis_client

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)
medical_assistant = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Import inside to prevent early loading
    import app.bot.handlers as handlers 
    from src.utils.redis_client import redis_client
    
    logger.info("🚀 FAST START: Port 8080 is now opening...")
    
    async def background_init():
        try:
            # WEBHOOK CHECK
            base_url = os.getenv("WEBHOOK_URL")
            if base_url:
                # webhook_path = f"{base_url.rstrip('/')}/webhook"
                webhook_path = os.getenv('WEBHOOK_URL', '')
                
                # Fetch current status from Telegram
                current_webhook = await handlers.bot.get_webhook_info()
                
                if current_webhook.url != webhook_path:
                    logger.info(f"🔄 Webhook mismatch. Updating: {current_webhook.url} -> {webhook_path}")
                    await handlers.bot.set_webhook(
                        url=webhook_path,
                        drop_pending_updates=True,
                        allowed_updates=["message", "callback_query"]
                    )
                else:
                    logger.info("✅ Webhook already correctly set. Skipping update.")
            else:
                logger.warning("⚠️ WEBHOOK_URL not found in env.")
                
            logger.info("🧠 Loading heavy AI libraries...")
            from src.synthesis.response_generator import ResponseGenerator
            
            await redis_client.init()
            await ResponseGenerator.initialize()
            
            # CRITICAL: Update the variable INSIDE the handlers module
            handlers.medical_assistant = ResponseGenerator()
            
            # Also update local global for the API endpoints
            global medical_assistant
            medical_assistant = handlers.medical_assistant
            
            logger.info("✅ AI LOADED AND READY")
        except Exception as e:
            logger.error(f"❌ AI INIT FAILED: {e}")

    asyncio.create_task(background_init())
    yield
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
        from app.bot.handlers import dp, bot
        data = await request.json()
        update = Update.model_validate(data) 
        await dp.feed_update(bot, update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return {"status": "error"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    if not medical_assistant:
        return {
            "status": "error", 
            "message": "AI is still initializing. Try again in 30 seconds."
            }
    
    structured = await asyncio.to_thread(
        medical_assistant.generate_structured,
        request.query
    )
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
    

@app.get("/")
@app.get("/health")
@app.get("/kaithheathcheck")
async def health():
    # If medical_assistant isn't ready, "starting" but the port is open
    is_ready = medical_assistant is not None
    return {
        "status": "healthy" if is_ready else "initializing",
        "service": "AI Medical Assistant",
        "ready": is_ready
    }
    

if __name__ == "__main__":
    import uvicorn
    # Render provides the port via an environment variable
    # If not found, it defaults to 8080
    port = int(os.environ.get("PORT", 8080))
    
    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
        
    
