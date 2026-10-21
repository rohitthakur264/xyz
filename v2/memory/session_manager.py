from typing import Dict, Optional
import time
from .doctor_context import DoctorContext
from .patient_context import PatientContext
from .visit_context import VisitContext
from config.logging import get_logger

logger = get_logger(__name__)

class SessionState:
    """Holds the active context for a specific session."""
    def __init__(self, session_id: str, doctor_id: str):
        self.session_id = session_id
        self.doctor = DoctorContext(doctor_id=doctor_id)
        self.patient: Optional[PatientContext] = None
        self.visit: Optional[VisitContext] = None
        self.pending_write: Optional[dict] = None
        self.last_sql: Optional[str] = None
        self.history: list = []
        self.created_at = time.time()
        self.last_accessed = time.time()

    def add_history(self, question: str, sql: str, rows_returned: int, intent: str, answer: str = ""):
        self.history.append({
            "question": question,
            "sql": sql,
            "rows": rows_returned,
            "intent": intent,
            "answer": answer,
            "timestamp": time.time()
        })
        self.last_sql = sql
        self.last_accessed = time.time()

    def get_context_summary(self) -> str:
        """Returns a string describing the current active context for the LLM."""
        ctx = []
        if self.patient:
            ctx.append(f"Active Patient Database Primary Key (patientid): {self.patient.patient_id}")
            if self.patient.registration_no:
                ctx.append(f"Active Patient Registration Number (registration_no): '{self.patient.registration_no}'")
            if self.patient.name:
                ctx.append(f"Active Patient Name: {self.patient.name}")
            ctx.append(f"NOTE: When querying transactional/clinical tables (e.g. fhir_visit_mst), filter by patientid = {self.patient.patient_id}")
        if self.visit:
            ctx.append(f"Active Visit ID: {self.visit.visit_id}")
        
        # Append recent chat history (last 3 interactions)
        if self.history:
            ctx.append("\n--- RECENT CHAT HISTORY ---")
            recent = self.history[-3:]
            for i, h in enumerate(recent, 1):
                ctx.append(f"User Question: {h['question']}")
                if h.get("answer"):
                    ctx.append(f"AI Assistant Response/Data:\n{h['answer']}")
                ctx.append("---------------------------")
        
        if not ctx:
            return "No patient or visit context is currently loaded. No chat history."
            
        return "\n".join(ctx)


class SessionManager:
    """Manages active sessions globally."""
    _sessions: Dict[str, SessionState] = {}

    @classmethod
    def get_or_create_session(cls, session_id: str, doctor_id: str) -> SessionState:
        if session_id not in cls._sessions:
            logger.info(f"Creating new session {session_id} for doctor {doctor_id}")
            cls._sessions[session_id] = SessionState(session_id, doctor_id)
        else:
            cls._sessions[session_id].last_accessed = time.time()
        return cls._sessions[session_id]
        
    @classmethod
    def end_session(cls, session_id: str):
        if session_id in cls._sessions:
            del cls._sessions[session_id]
            logger.info(f"Ended session {session_id}")
