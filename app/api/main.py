# app/api/main.py

import sys
import os
import uuid
import time
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from aiogram.types import Update

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.redis_client import redis_client
from app.bot.handlers import dp, bot, medical_assistant

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)
medical_assistant = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global medical_assistant
    logger.info("🚀 FAST START: Port 8080 is now opening...")
    
    # Run heavy loading in a separate thread so Uvicorn can finish starting
    async def background_init():
        global medical_assistant
        try:
            logger.info("🧠 Loading heavy AI libraries...")
            # LOCAL IMPORTS: This prevents the app from hanging on boot
            from src.synthesis.response_generator import ResponseGenerator
            from scripts.bootstrap import bootstrap_pipeline
            
            # Initialize Redis
            from src.utils.redis_client import redis_client
            await redis_client.init()

            if os.getenv("RUN_BOOTSTRAP", "false") == "true":
                await asyncio.to_thread(bootstrap_pipeline)
            
            await ResponseGenerator.initialize()
            medical_assistant = ResponseGenerator()
            logger.info("✅ AI LOADED AND READY")
        except Exception as e:
            logger.error(f"❌ AI INIT FAILED: {e}")

    # Fire and forget the heavy stuff
    asyncio.create_task(background_init())
    yield

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



# MANDATORY: Add every path Leapcell is trying to hit
@app.get("/")
@app.get("/health")
@app.get("/kaithheathcheck")
async def health():
    # If medical_assistant isn't ready, "starting" but the port is open
    is_ready = medical_assistant is not None
    return {
        "status": "healthy" if is_ready else "initializing",
        "service": "Medical Assistant",
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
    
