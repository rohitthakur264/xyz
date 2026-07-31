from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

# These would ideally be injected via FastAPI dependencies, but for now we'll mock global instances
# In a real app, we'd initialize these in main.py and pass them in or use app.state
# For simplicity, we assume they are initialized elsewhere and accessible.

class ChatRequest(BaseModel):
    session_id: str
    doctor_id: str
    question: str

class ChatResponse(BaseModel):
    answer: str
    sql: str
    intent: str
    tables: list

# Placeholder for the global orchestrator instance
orchestrator = None

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
        
    try:
        res = orchestrator.handle_message(
            session_id=request.session_id,
            doctor_id=request.doctor_id,
            question=request.question
        )
        return ChatResponse(**res)
    except Exception as e:
        from config.logging import get_logger
        get_logger(__name__).error(f"Error handling chat message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
