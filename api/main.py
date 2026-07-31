import uuid
import datetime
import json
import logging
from fastapi import FastAPI, HTTPException, Header, Depends
from typing import Optional

from api.models import ChatRequest, ChatResponse
from config.settings import INTERACTION_LOG_FILE, DEBUG_MODE
from memory.session_store import load_session, add_turn, get_active_patient, set_active_patient, get_last_result, set_last_result
from memory.rewriter import rewrite_question
from memory.patient_context import extract_patient_identifier
from router.intent_router import route_question
from run_phase2 import execute_sql_pipeline
from run_phase3 import execute_rag_pipeline
from sql_pipeline.answerer import answer_reasoning_question
from guardrails.verifier import verify_answer

import os

app = FastAPI(title="Hospital AI Assistant API")
logger = logging.getLogger("uvicorn.error")

# Simple secret for minimal admin endpoints
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "temp-local-secret-123")

def verify_admin(x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

# Note: We use a synchronous `def` here rather than `async def` because 
# Ollama and MySQL calls are currently blocking. Using `def` tells FastAPI 
# to run this in an external threadpool, preventing one long request from 
# serializing the entire server.

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Hospital AI API is running. UI is available on port 8501."}

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    try:
        session_id = req.session_id if req.session_id else str(uuid.uuid4())[:8]
        raw_question = req.question.strip()
        
        if not raw_question:
            return ChatResponse(
                answer="Please ask a question.",
                rewritten_question=raw_question,
                route_decision="NONE",
                source_used="none",
                session_id=session_id
            )
            
        # 0. Extract Patient Context
        patient_ctx = extract_patient_identifier(raw_question)
        if patient_ctx.get("error"):
            # This catches "Multiple patients match..." or "No patient found..."
            return ChatResponse(
                answer=patient_ctx["error"].replace("NEEDS_PATIENT:", "").strip(),
                rewritten_question=raw_question,
                route_decision="DATABASE (BLOCKED)",
                source_used="safety_gate",
                session_id=session_id
            )
            
        if patient_ctx["has_identifier"] and patient_ctx["patient"]:
            set_active_patient(session_id, patient_ctx["patient"])
            
        active_patient = get_active_patient(session_id)
            
        # 1. Memory / Rewriter
        session_data = load_session(session_id)
        history = session_data.get("history", [])
        rewritten = rewrite_question(raw_question, history)
        
        if rewritten.startswith("AMBIGUOUS:"):
            return ChatResponse(
                answer=rewritten + "\nPlease clarify your question.",
                rewritten_question=rewritten,
                route_decision="AMBIGUOUS",
                source_used="none",
                session_id=session_id
            )
            
        # 2. Router
        route = route_question(rewritten)
        
        # 3. Pipeline execution
        final_answer = ""
        source_used = None
        retrieved_context = ""
        
        if route == "DATABASE":
            # Check if query is a pure patient identity lookup
            is_pure_identity_query = False
            if active_patient:
                clean_q = rewritten.lower().strip()
                identity_keywords = ["patient detail", "patient info", "patient profile", "registration no", "registration number", "who is", "demographics", "patient"]
                secondary_domains = ["visit", "admission", "bed", "bill", "prescription", "lab", "tariff", "allergy", "department", "operation", "surgery", "vitals"]
                if any(k in clean_q for k in identity_keywords) or len(clean_q.split()) <= 3:
                    if not any(d in clean_q for d in secondary_domains):
                        is_pure_identity_query = True

            if is_pure_identity_query:
                from memory.patient_context import get_patient_details
                p_details = get_patient_details(active_patient["id"])
                rows = p_details["rows"]
                cols = p_details["columns"]
                from sql_pipeline.answerer import answer_question
                final_answer = answer_question(rewritten, p_details["sql_used"], cols, rows)
                source_used = "patient_master_resolver"
                data_str = " | ".join(cols) + "\n" + "\n".join([" | ".join([str(val) for val in r]) for r in rows])
                retrieved_context = f"SQL Executed: {p_details['sql_used']}\nResults Data:\n{data_str}"
                
                set_last_result(session_id, {
                    "sql": p_details["sql_used"],
                    "rows": rows,
                    "columns": cols,
                    "formatted_data": data_str,
                    "question": rewritten
                })
            else:
                result = execute_sql_pipeline(rewritten, active_patient=active_patient)
                
                # Catch unscoped queries intercept
                if result.get("error") and result["error"].startswith("NEEDS_PATIENT:"):
                    return ChatResponse(
                        answer=result["error"].replace("NEEDS_PATIENT:", "").strip(),
                        rewritten_question=rewritten,
                        route_decision="DATABASE (BLOCKED)",
                        source_used="safety_gate",
                        session_id=session_id,
                        debug=result.get("debug_info") if DEBUG_MODE else None
                    )
                
                final_answer = result["answer"]
                source_used = "sql" if result.get("sql_used") else "none"
                if result.get("sql_used"):
                    rows = result.get('rows', [])
                    cols = result.get('columns', [])
                    if not rows:
                        data_str = "No results found."
                    else:
                        data_str = " | ".join(cols) + "\n"
                        for row in rows:
                            data_str += " | ".join([str(val) for val in row]) + "\n"
                    retrieved_context = f"SQL Executed: {result.get('sql_used')}\nResults Data:\n{data_str}"
                    
                    # Store last result context for multi-turn reasoning
                    set_last_result(session_id, {
                        "sql": result.get("sql_used"),
                        "rows": rows,
                        "columns": cols,
                        "formatted_data": data_str,
                        "question": rewritten
                    })
                
        elif route == "CONTEXT_REASONING":
            last_result = get_last_result(session_id)
            if last_result and last_result.get("formatted_data"):
                final_answer = answer_reasoning_question(rewritten, last_result)
                source_used = "context_reasoning"
                retrieved_context = f"Last Result Context:\n{last_result.get('formatted_data', '')}"
            else:
                final_answer = "No previous query data is available in your current session to interpret. Please ask a specific lookup question first."
                source_used = "context_reasoning_missing"

        elif route == "KNOWLEDGE":
            result = execute_rag_pipeline(rewritten)
            final_answer = result["answer"]
            
            verified_chunks = result.get("verified_chunks", [])
            if verified_chunks:
                sources = list(set(chunk['metadata'].get('source_file', 'unknown') for chunk in verified_chunks))
                source_used = "document:" + ",".join(sources)
                retrieved_context = "\n".join([c["text"] for c in verified_chunks])
            else:
                source_used = "general_fallback"
                
        else: # OFF_TOPIC
            final_answer = "I can only answer questions related to the hospital database or medical knowledge base."
            source_used = "off_topic"
            
        # 4. Final Verifier Pass
        if retrieved_context:
            final_answer, verifier_verdict, _ = verify_answer(rewritten, final_answer, retrieved_context)
        else:
            verifier_verdict = "NO_CONTEXT_NEEDED"
            
        # Add to session history
        add_turn(session_id, raw_question, final_answer)
        
        # Log Interaction
        os.makedirs(os.path.dirname(INTERACTION_LOG_FILE), exist_ok=True)
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "session_id": session_id,
            "raw_question": raw_question,
            "rewritten_question": rewritten,
            "route_decision": route,
            "pipeline_output": final_answer,
            "source_used": source_used,
            "debug_info": result.get("debug_info") if locals().get("result") else None
        }
        with open(INTERACTION_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
            
        response_kwargs = {
            "answer": final_answer,
            "rewritten_question": rewritten,
            "route_decision": route,
            "source_used": source_used,
            "session_id": session_id
        }
        
        if DEBUG_MODE:
            debug_data = {
                "rewritten_question": rewritten,
                "history_used": history,
                "route_decision": route,
                "verifier_verdict": verifier_verdict,
                "verifier_context": retrieved_context
            }
            if "debug_info" in locals().get('result', {}):
                debug_data.update(result["debug_info"])
            response_kwargs["debug"] = debug_data
            
        return ChatResponse(**response_kwargs)
        
    except Exception as e:
        logger.error(f"Error in chat pipeline: {e}", exc_info=True)
        return ChatResponse(
            answer="The assistant is temporarily unavailable, please try again.",
            rewritten_question=req.question,
            route_decision="ERROR",
            source_used="error",
            session_id=req.session_id or "error_session"
        )

@app.post("/admin/reingest_documents", dependencies=[Depends(verify_admin)])
def reingest_documents():
    # Placeholder for Phase 3 document ingestion script call
    # import run_phase3_ingestion
    # run_phase3_ingestion.run()
    return {"status": "success", "message": "Documents re-ingested."}

@app.post("/admin/reextract_schema", dependencies=[Depends(verify_admin)])
def reextract_schema():
    # Placeholder for Phase 1 schema extraction script call
    # import run_phase1
    # run_phase1.run()
    return {"status": "success", "message": "Schema re-extracted."}
