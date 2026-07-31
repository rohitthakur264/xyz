from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    rewritten_question: str
    route_decision: str
    source_used: str
    session_id: str
    debug: Optional[dict] = None
