# app/api/models.py

from pydantic import BaseModel, Field
from typing import List, Optional, Dict 

class ResponseBlock(BaseModel):
    header: str
    content: str  # Markdown formatted string
    type: str     # 'summary', 'list', 'urgency', 'disclaimer'

class ChatResponse(BaseModel):
    query_id: str
    session_id: str
    condition_detected: str
    urgency_level: str
    summary: str
    urgency_friendly: str
    available_sections: List[Dict[str, str]]
    sections: Optional[Dict] = None
    latency_ms: float
    

class ChatRequest(BaseModel):
    query: str = Field(..., example="I have a sharp pain in my lower back")
    session_id: Optional[str] = None


class ProfileUpdate(BaseModel):
    age: int
    chronic_conditions: List[str]
    recent_symptoms: Optional[List[str]] = []