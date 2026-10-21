from fastapi import APIRouter, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import json
import os
from config.logging import audit_logger, get_logger

class ChatRequest(BaseModel):
    session_id: str
    question: str

class ChatResponse(BaseModel):
    answer: str
    sql: str
    intent: str
    tables: list
    patient: Optional[dict] = None
    raw_data: Optional[list] = None
    add_record_form: Optional[dict] = None

# Placeholder for the global orchestrator instance
orchestrator = None

router = APIRouter()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_authenticated_doctor(api_key: Optional[str] = Security(api_key_header), api_key_query: Optional[str] = None) -> dict:
    key_to_use = api_key or api_key_query
    
    default_mapping = '{"password": {"name": "dr.Yashmin", "empid": 530}}'
    mapping_str = os.getenv("API_KEYS_MAP", default_mapping)
    try:
        API_KEYS_MAP = json.loads(mapping_str)
    except Exception:
        API_KEYS_MAP = {}
        
    doctor_data = API_KEYS_MAP.get(key_to_use)
    if not doctor_data:
        try:
            audit_logger.log_interaction(
                session_id="UNAUTHORIZED",
                doctor_id="UNKNOWN",
                patient_id=None,
                intent="UNAUTHORIZED_ACCESS",
                question="Attempted access with invalid API key",
                sql="",
                rows_returned=0,
                answer="401 Invalid API key",
                execution_time_ms=0,
                retries=0,
                validation_errors=[]
            )
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="Invalid API key")
        
    if isinstance(doctor_data, str):
        return {"name": doctor_data, "empid": 377} # Fallback for old string mapping
    return doctor_data

@router.get("/doctors")
async def list_doctors():
    """Public list of registered doctor names (for the login screen's
    dropdown) — sourced from the same API_KEYS_MAP env var, but this
    endpoint only ever returns the NAMES, never the keys. No auth
    required to view this list (it's just names, not a secret), but every
    other endpoint still requires the matching key."""
    default_mapping = '{"password": {"name": "dr.Yashmin", "empid": 530}}'
    mapping_str = os.getenv("API_KEYS_MAP", default_mapping)
    try:
        API_KEYS_MAP = json.loads(mapping_str)
    except Exception:
        API_KEYS_MAP = {}
        
    names = []
    for val in API_KEYS_MAP.values():
        if isinstance(val, str):
            names.append(val)
        else:
            names.append(val.get("name"))
    return {"doctors": sorted(set(names))}

@router.get("/whoami")
async def whoami(doctor_info: dict = Depends(get_authenticated_doctor)):
    """Resolves the caller's API key to their doctor_id via API_KEYS_MAP
    (env-configured, not hardcoded) — lets the UI show 'Logged in as: X'
    without duplicating the key->doctor mapping in the frontend."""
    return {"doctor_id": doctor_info["name"]}

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, doctor_info: dict = Depends(get_authenticated_doctor)):
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
        
    try:
        res = orchestrator.handle_message(
            session_id=request.session_id,
            doctor_id=doctor_info["name"],
            question=request.question
        )
        return ChatResponse(**res)
    except Exception as e:
        from config.logging import get_logger
        get_logger(__name__).error(f"Error handling chat message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export/preview/session/{session_id}")
async def preview_patient_record(session_id: str, doctor_info: dict = Depends(get_authenticated_doctor)):
    from memory.session_manager import SessionManager
    from services.document_generator import DocumentGenerator
    
    session = SessionManager.get_or_create_session(session_id, doctor_info["name"])
    if not session.patient:
        raise HTTPException(status_code=400, detail="No active patient in this session.")
        
    try:
        generator = DocumentGenerator()
        record_data = generator.build_record_data(session.patient)
        markdown_text = generator.render_markdown(record_data)
        return {"markdown": markdown_text}
    except Exception as e:
        from config.logging import get_logger
        get_logger(__name__).error(f"Error generating preview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export/session/{session_id}/full-record")
async def export_patient_record(session_id: str, doctor_info: dict = Depends(get_authenticated_doctor)):
    from memory.session_manager import SessionManager
    from services.document_generator import DocumentGenerator
    from config.logging import audit_logger
    import os

    session = SessionManager.get_or_create_session(session_id, doctor_info["name"])
    if not session.patient:
        raise HTTPException(status_code=400, detail="No active patient in this session.")
        
    try:
        generator = DocumentGenerator()
        record_data = generator.build_record_data(session.patient)
        file_path = generator.render_docx(record_data)
        
        # Audit Log for the export
        try:
            audit_logger.log_interaction(
                session_id=session_id,
                doctor_id=doctor_info["name"],
                patient_id=session.patient.patient_id,
                intent="MEDICAL_RECORD_EXPORT",
                question="Export complete medical record (Word Doc)",
                sql="N/A (Deterministic)",
                rows_returned=0,
                answer=f"Exported to {os.path.basename(file_path)}",
                execution_time_ms=0,
                retries=0,
                validation_errors=[]
            )
        except Exception as e:
            from config.logging import get_logger
            get_logger(__name__).warning(f"Audit log failed for export: {e}")

        return FileResponse(
            file_path, 
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            filename=f"Patient_Record_{session.patient.patient_id}.docx"
        )
    except Exception as e:
        from config.logging import get_logger
        get_logger(__name__).error(f"Error generating document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export/session/{session_id}/transcript")
async def export_consultation_transcript(session_id: str, doctor_info: dict = Depends(get_authenticated_doctor)):
    from memory.session_manager import SessionManager
    from services.document_generator import DocumentGenerator
    from config.logging import audit_logger
    import os

    session = SessionManager.get_or_create_session(session_id, doctor_info["name"])
    if not session.patient:
        raise HTTPException(status_code=400, detail="No active patient in this session.")
        
    try:
        generator = DocumentGenerator()
        file_path = generator.render_transcript_docx(session)
        
        # Audit Log for the export
        try:
            audit_logger.log_interaction(
                session_id=session_id,
                doctor_id=doctor_info["name"],
                patient_id=session.patient.patient_id,
                intent="TRANSCRIPT_EXPORT",
                question="Export consultation transcript (Word Doc)",
                sql="N/A (Session History)",
                rows_returned=0,
                answer=f"Exported to {os.path.basename(file_path)}",
                execution_time_ms=0,
                retries=0,
                validation_errors=[]
            )
        except Exception as e:
            from config.logging import get_logger
            get_logger(__name__).warning(f"Audit log failed for export: {e}")

        return FileResponse(
            file_path, 
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            filename=f"Consultation_Transcript_{session.patient.patient_id}.docx"
        )
    except Exception as e:
        from config.logging import get_logger
        get_logger(__name__).error(f"Error generating document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------ #
# Write path: Add Record (prescription / lab test / vitals / ...)
# ------------------------------------------------------------------ #

class InsertRecordRequest(BaseModel):
    session_id: str
    entity_type: str
    field_values: dict

@router.get("/records/entities")
async def list_insertable_entities(doctor_info: dict = Depends(get_authenticated_doctor)):
    """Which record types can be added from the UI, for populating the
    'Add Record' type selector."""
    from services import insert_service
    return {"entities": insert_service.list_entities()}

@router.get("/records/form/{entity_type}")
async def get_record_form(entity_type: str, doctor_info: dict = Depends(get_authenticated_doctor)):
    """Field definitions for one entity, so the UI can render inputs
    without hardcoding form fields."""
    from services import insert_service
    try:
        schema = insert_service.get_form_schema(entity_type)
        return {"entity_type": entity_type, "schema": schema}
    except insert_service.InsertValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/records/lookup/{entity_type}/{field_key}")
async def get_lookup_options(entity_type: str, field_key: str, doctor_info: dict = Depends(get_authenticated_doctor)):
    """Dropdown options for a 'lookup' type field (e.g. drug name)."""
    from services import insert_service
    schema = insert_service.get_form_schema(entity_type)
    field = next((f for f in schema.get("fields", []) if f["key"] == field_key), None)
    if not field or field.get("type") != "lookup":
        raise HTTPException(status_code=400, detail=f"'{field_key}' is not a lookup field on '{entity_type}'.")
    try:
        options = insert_service.get_lookup_options(
            field["lookup_table"], field["lookup_id_col"], field["lookup_display_col"]
        )
        return {"options": options}
    except Exception as e:
        from config.logging import get_logger
        get_logger(__name__).error(f"Lookup failed for {entity_type}.{field_key}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not load options right now.")

@router.get("/records/lookup-search/{entity_type}/{field_key}")
async def search_lookup_options(entity_type: str, field_key: str, q: str, doctor_info: dict = Depends(get_authenticated_doctor)):
    """Top-5 fuzzy suggestions for a 'lookup' field as the user types (e.g.
    'Para' -> Paracetamol, Paracip, ...). Read-only. Reused by the chat
    write-flow's 'did you mean?' prompts, and available generically for
    any future autocomplete-style UI without needing new backend work."""
    from services import insert_service
    schema = insert_service.get_form_schema(entity_type)
    field = next((f for f in schema.get("fields", []) if f["key"] == field_key), None)
    if not field or field.get("type") != "lookup":
        raise HTTPException(status_code=400, detail=f"'{field_key}' is not a lookup field on '{entity_type}'.")
    try:
        matches = insert_service.find_lookup_matches(
            field["lookup_table"], field["lookup_id_col"], field["lookup_display_col"], q, limit=5
        )
        return {"matches": matches}
    except Exception as e:
        from config.logging import get_logger
        get_logger(__name__).error(f"Lookup search failed for {entity_type}.{field_key}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not search right now.")

@router.post("/records/insert")
async def insert_record(request: InsertRecordRequest, doctor_info: dict = Depends(get_authenticated_doctor)):
    from memory.session_manager import SessionManager
    from services import insert_service
    from config.settings import ENABLE_WRITE_OPERATIONS

    if not ENABLE_WRITE_OPERATIONS:
        raise HTTPException(status_code=403, detail="Write operations are disabled. Set ENABLE_WRITE_OPERATIONS=true after verifying insert_schema.json.")

    session = SessionManager.get_or_create_session(request.session_id, doctor_info["name"])
    if not session.patient:
        raise HTTPException(status_code=400, detail="No active patient in this session. Search for a patient first.")
    if not session.visit:
        raise HTTPException(status_code=400, detail="No active visit in this session. Select a visit first.")

    result = insert_service.insert_record(
        entity_key=request.entity_type,
        patient_id=session.patient.patient_id,
        visit_id=session.visit.visit_id,
        doctor_name=doctor_info["name"],
        doctor_empid=doctor_info.get("empid"),
        field_values=request.field_values,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    # Clear any stale chat-side pending confirmation — the doctor confirmed
    # via the UI form instead, so a lingering "type confirm/cancel" prompt
    # in chat would be confusing and refer to a request that's now moot.
    session.pending_write = None
    return result
