# app/api/main.py

import sys
import os
import uuid
import time
import json
import logging
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from app.api.models import ChatResponse, ChatRequest, ProfileUpdate
from pydantic import BaseModel, Field
from typing import List, Optional
from src.synthesis.response_generator import ResponseGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="NHS-Based Medical RAG API",
    description="Secure API for medical symptom analysis and triage guidance.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with UI URL
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global singleton (pre-loaded)
medical_assistant: ResponseGenerator = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern replacement for deprecated on_event('startup')"""
    global medical_assistant
    print("🚀 Starting FastAPI – Pre-loading Medical Assistant...")
    ResponseGenerator.initialize()          # ← Pre-loads embeddings, FAISS, lexicon
    medical_assistant = ResponseGenerator()
    yield
    print("🛑 FastAPI shutting down...")

app = FastAPI(lifespan=lifespan)  # ← Apply lifespan

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": time.time()}

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    start_time = time.time()
    session_id = request.session_id or str(uuid.uuid4())[:8]
    
    structured = medical_assistant.generate_structured(request.query)
    
    return {
        "query_id": structured["query_id"],
        "session_id": session_id,
        "condition_detected": structured["condition"],
        "urgency_level": structured["urgency_level"],
        "summary": structured["summary"],
        "urgency_friendly": structured["urgency_friendly"],
        "available_sections": structured["available_sections"],
        "sections": structured["sections"],
        "latency_ms": structured["latency_ms"]
    }

@app.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """
    Streams the LLM response token-by-token for a 'typing' effect.
    """
    session_id = request.session_id or str(uuid.uuid4())[:8]

    async def event_generator():
        full_text = ""
        
        # We call a new streaming method in our generator
        # Note: ChatGoogleGenerativeAI supports .astream()
        async for chunk in medical_assistant.stream_generate(request.query):
            content = chunk.content
            full_text += content
            
            # Format as an SSE message
            # 'data: ' is the standard prefix for Server-Sent Events
            yield f"data: {json.dumps({'type': 'token', 'text': content})}\n\n"

        # Final packet: Send the structured analysis after the stream finished
        structured_blocks = medical_assistant._parse_to_blocks(full_text)
        urgency = "LOW"
        if "Urgency: HIGH" in full_text: urgency = "HIGH"
        elif "Urgency: MEDIUM" in full_text: urgency = "MEDIUM"

        final_metadata = {
            "type": "final",
            "session_id": session_id,
            "urgency_level": urgency,
            "blocks": structured_blocks
        }
        yield f"data: {json.dumps(final_metadata)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.put("/profile")
async def update_profile(profile: ProfileUpdate):
    """Update the user's medical profile for personalized retrieval."""
    medical_assistant.profile.update(profile.dict())
    medical_assistant.save_profile()
    return {"message": "Profile updated successfully"}