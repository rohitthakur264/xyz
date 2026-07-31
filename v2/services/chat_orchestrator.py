from typing import Optional
from memory.session_manager import SessionManager
from sql_pipeline.intent_detector import IntentDetector
from sql_pipeline.query_planner import QueryPlanner
from sql_pipeline.sql_corrector import SQLCorrector
from llm.answer_generator import AnswerGenerator
from services.patient_resolver import PatientResolver
from config.logging import get_logger, audit_logger
import time

logger = get_logger(__name__)

class ChatOrchestrator:
    """The central entrypoint for processing user queries."""
    
    def __init__(self, intent_detector: IntentDetector, query_planner: QueryPlanner, sql_corrector: Optional[SQLCorrector] = None, answer_generator: Optional[AnswerGenerator] = None, patient_resolver: Optional[PatientResolver] = None):
        self.intent_detector = intent_detector
        self.query_planner = query_planner
        self.sql_corrector = sql_corrector
        self.answer_generator = answer_generator
        self.patient_resolver = patient_resolver or PatientResolver()

    def handle_message(self, session_id: str, doctor_id: str, question: str) -> dict:
        """
        Process an incoming chat message.
        """
        start_time = time.time()
        logger.info(f"Orchestrator received question from Session {session_id}: {question}")
        
        # 1. Load Session Context
        session = SessionManager.get_or_create_session(session_id, doctor_id)
        
        # 2. Extract & Resolve Patient Context if missing or specified in prompt
        resolved_patient = self.patient_resolver.resolve_from_question(question)
        if resolved_patient:
            session.patient = resolved_patient
            logger.info(f"Set session patient context: ID={session.patient.patient_id}")

        # 3. Detect Intent
        intent = self.intent_detector.detect_intent(question)
        
        # 4. Plan Query (Fetch tables, examples, context)
        plan = self.query_planner.plan_query(question, intent, session)
        
        # 5. Generate, Validate, and Execute SQL (if sql_corrector available)
        sql = ""
        retries = 0
        validation_errors = []
        rows_returned = 0
        answer = ""
        
        if self.sql_corrector:
            try:
                pipeline_result = self.sql_corrector.run_pipeline(question, plan)
                sql = pipeline_result.get("sql", "")
                retries = pipeline_result.get("retries", 0)
                validation_errors = pipeline_result.get("final_errors", [])
                res_dict = pipeline_result.get("result") or {}
                
                if res_dict.get("success"):
                    rows = res_dict.get("rows", [])
                    rows_returned = len(rows)
                    if self.answer_generator:
                        answer = self.answer_generator.generate(question, sql, rows)
                    else:
                        answer = f"Query executed successfully returning {rows_returned} rows."
                else:
                    rows_returned = 0
                    err_detail = res_dict.get("error", "Unknown error")
                    answer = f"I encountered an error querying the database: {err_detail}"
            except Exception as pipeline_err:
                logger.error(f"Pipeline execution error: {pipeline_err}", exc_info=True)
                rows_returned = 0
                answer = f"I encountered an error processing your query: {pipeline_err}"
        else:
            answer = "SQL execution pipeline unavailable."
        
        # 5. Update Session History
        session.add_history(question, sql, rows_returned, intent)
        
        execution_time = (time.time() - start_time) * 1000
        
        # 6. Audit Log
        try:
            audit_logger.log_interaction(
                session_id=session_id,
                doctor_id=doctor_id,
                patient_id=session.patient.patient_id if session.patient else None,
                intent=intent,
                question=question,
                sql=sql,
                rows_returned=rows_returned,
                answer=answer,
                execution_time_ms=execution_time,
                retries=retries,
                validation_errors=validation_errors
            )
        except Exception as e:
            logger.warning(f"Audit log failed: {e}")
        
        return {
            "answer": answer,
            "sql": sql,
            "intent": intent,
            "tables": plan["tables"]
        }
