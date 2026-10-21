from typing import Optional
from memory.session_manager import SessionManager
from sql_pipeline.intent_detector import IntentDetector
from sql_pipeline.query_planner import QueryPlanner
from sql_pipeline.sql_corrector import SQLCorrector
from llm.answer_generator import AnswerGenerator
from services.patient_resolver import PatientResolver
from database.connection_pool import get_connection
from config.logging import get_logger, audit_logger
import time
import json
import os
import copy
import concurrent.futures
from services.visit_resolver import VisitResolver


def _classify_followup_context(question: str, llm_client, model: str) -> tuple[Optional[str], bool]:
    """Determines (a) which clinical domain a conversational follow-up
    refers to (for reverse-scanning session history), and (b) whether it's
    asking for a normal/abnormal evaluation (structured table) vs a general
    explanation (prose). Uses the LLM instead of hardcoded English keyword
    lists ("lab", "normal", "vital", ...) so Hinglish, synonyms, and typos
    are handled the same way as everything else in this app — a follow-up
    like "iski test report normal hai kya" must resolve to LAB/evaluative
    just as reliably as "is the lab report normal?".

    Only called from the CONVERSATIONAL/GENERAL bypass path when there's
    session history to disambiguate against, so this doesn't add a call to
    every message — only to follow-up questions that need it.

    Falls back to (None, False) on any parse failure - the same safe
    default as "no domain hint, treat as a plain explanation" that the
    code had before this used the LLM.
    """
    prompt = """Classify a doctor's follow-up question in a hospital chat assistant. The question may be in English, Hindi, or Hinglish.

Respond with ONLY valid JSON in this exact shape, no explanation:
{"domain": "VITALS"|"LAB"|"SURGERY"|"ALLERGY"|"PRESCRIPTION"|null, "is_evaluative": true|false}

- "domain": which clinical data type the question is asking about/referring back to. Use null if it doesn't clearly refer to one of these five.
- "is_evaluative": true if the doctor is asking whether a previously-shown result is normal/abnormal/high/low/concerning/in-range (wants a normal-vs-actual assessment). false if they're asking something else about it (e.g. "what does this mean", "explain this drug", "post-care instructions").

Examples:
Question: "is the blood pressure normal?"
Response: {"domain": "VITALS", "is_evaluative": true}

Question: "iski test report theek hai kya?"
Response: {"domain": "LAB", "is_evaluative": true}

Question: "what does paracetamol do?"
Response: {"domain": "PRESCRIPTION", "is_evaluative": false}

Question: "precautions after the surgery?"
Response: {"domain": "SURGERY", "is_evaluative": false}

Question: "hi there"
Response: {"domain": null, "is_evaluative": false}

Question: \"""" + question + """\"
Response:"""

    try:
        raw = llm_client.generate(prompt, model=model, temperature=0.0).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)
        domain = parsed.get("domain")
        if domain not in ("VITALS", "LAB", "SURGERY", "ALLERGY", "PRESCRIPTION"):
            domain = None
        is_evaluative = bool(parsed.get("is_evaluative", False))
        return domain, is_evaluative
    except Exception as e:
        logger = get_logger(__name__)
        logger.warning(f"_classify_followup_context: could not parse LLM output ({e}); using safe defaults.")
        return None, False
logger = get_logger(__name__)



class ChatOrchestrator:
    """The central entrypoint for processing user queries."""
    
    def __init__(self, intent_detector: IntentDetector, query_planner: QueryPlanner, sql_corrector: Optional[SQLCorrector] = None, answer_generator: Optional[AnswerGenerator] = None, patient_resolver: Optional[PatientResolver] = None):
        self.intent_detector = intent_detector
        self.query_planner = query_planner
        self.sql_corrector = sql_corrector
        self.answer_generator = answer_generator
        self.patient_resolver = patient_resolver or PatientResolver()
        self.visit_resolver = VisitResolver()

    def _find_clinical_alternatives(self, typed_name: str, lookup_table: str, id_col: str, display_col: str) -> tuple[list[dict], str]:
        """Uses the LLM to identify the generic composition of an unknown drug,
        and searches the database for available alternatives."""
        if not self.answer_generator or not hasattr(self.answer_generator, "llm"):
            return [], ""
            
        prompt = f"""The doctor prescribed '{typed_name}'. This exact brand/medicine is not in our hospital inventory database.
What is the generic name, active ingredient, or main chemical composition of this drug?
Respond with ONLY the generic name/active ingredient, nothing else. Keep it as short as possible (e.g. 'Paracetamol' or 'Amoxicillin')."""
        generic_name = self.answer_generator.llm.generate(prompt, temperature=0.0).strip()
        if not generic_name or len(generic_name) < 3:
            return [], ""
            
        conn = get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            if lookup_table == "fhir_drug_mst":
                # Search by generic name/active ingredient in both display and scientificnm
                query = f"SELECT `{id_col}` AS id, `{display_col}` AS label FROM `{lookup_table}` WHERE `{display_col}` LIKE %s OR `scientificnm` LIKE %s LIMIT 10"
                cursor.execute(query, (f"%{generic_name}%", f"%{generic_name}%"))
            else:
                query = f"SELECT `{id_col}` AS id, `{display_col}` AS label FROM `{lookup_table}` WHERE `{display_col}` LIKE %s LIMIT 10"
                cursor.execute(query, (f"%{generic_name}%",))
                
            rows = cursor.fetchall()
            return rows, generic_name
        except Exception as e:
            logger.error(f"Error finding clinical alternatives for {typed_name}: {e}")
            return [], ""
        finally:
            conn.close()

    def handle_message(self, session_id: str, doctor_id: str, question: str) -> dict:
        """
        Process an incoming chat message.
        """
        start_time = time.time()
        logger.info(f"Orchestrator received question from Session {session_id}: {question}")
        
        # 1. Load Session Context
        session = SessionManager.get_or_create_session(session_id, doctor_id)

        # 1b. If a write is awaiting confirmation, handle confirm/cancel
        # BEFORE anything else (patient resolution, intent detection, etc.)
        # so a stray "yes"/"cancel" can't be misinterpreted. Nothing is
        # executed here unless the doctor's message is an explicit confirm.
        if session.pending_write:
            q_stripped = question.strip().lower()
            CONFIRM_WORDS = {"confirm", "yes", "y", "haan", "ha", "confirm karo", "ok", "okay"}
            CANCEL_WORDS = {"cancel", "no", "n", "nahi", "nahi karo", "stop"}

            if q_stripped in CONFIRM_WORDS:
                pw = session.pending_write
                # Time-boxed: don't execute a stale confirmation against
                # context that may have changed (e.g. patient switched).
                if time.time() - pw["created_at"] > 300:
                    session.pending_write = None
                    return {"answer": "That request timed out (5 min). Please re-enter it.", "sql": "", "intent": "ADD_RECORD", "tables": []}

                from services import insert_service
                # Re-validate at confirm time (not just re-use what was
                # computed when the form was first shown) — covers the case
                # where required fields were still missing/unresolved back
                # then (e.g. an unmatched drug name) and the doctor typed
                # "confirm" instead of using the review form to fix it.
                revalidation = insert_service.validate_only(pw["entity_type"], pw.get("raw_field_values", pw["cleaned_field_values"]))
                if not revalidation["valid"]:
                    if revalidation["missing"]:
                        answer = f"Still missing: {', '.join(revalidation['missing'])}. Please fill these in the form above, or retype with the missing details."
                    else:
                        answer = f"That doesn't look valid: {revalidation['error']}"
                    return {"answer": answer, "sql": "", "intent": "ADD_RECORD", "tables": []}

                result = insert_service.insert_cleaned_record(
                    entity_key=pw["entity_type"],
                    patient_id=pw["patient_id"],
                    visit_id=pw["visit_id"],
                    doctor_id=doctor_id,
                    cleaned_field_values=revalidation["cleaned"],
                )
                session.pending_write = None
                if result["success"]:
                    answer = f"✅ Saved. Record ID: {result['record_id']}"
                else:
                    answer = f"❌ Could not save: {result['error']}"
                session.add_history(question, "", 0, "ADD_RECORD", answer)
                return {"answer": answer, "sql": "", "intent": "ADD_RECORD", "tables": []}

            elif q_stripped in CANCEL_WORDS:
                session.pending_write = None
                answer = "Cancelled. Nothing was saved."
                session.add_history(question, "", 0, "ADD_RECORD", answer)
                return {"answer": answer, "sql": "", "intent": "ADD_RECORD", "tables": []}

            else:
                # Ambiguous while a write is pending — don't guess, don't
                # silently drop the pending write either. Force an explicit
                # decision so nothing executes on a misread message.
                answer = "You have an unsaved record waiting — please reply **'confirm'** to save it or **'cancel'** to discard it before asking anything else."
                return {"answer": answer, "sql": "", "intent": "ADD_RECORD", "tables": []}

        # 2. Extract & Resolve Patient Context if missing or specified in prompt
        resolved_patient = self.patient_resolver.resolve_from_question(question)
        if resolved_patient:

            if not session.patient or session.patient.patient_id != resolved_patient.patient_id:
                # Explicitly clear active visit on a successful patient switch
                session.visit = None
                
            session.patient = resolved_patient
            logger.info(f"Set session patient context: ID={session.patient.patient_id}")
            
        # 2b. Optionally resolve a visit from a standalone query if mentioned explicitly
        if session.patient:
            resolver = VisitResolver()
            visits = resolver.fetch_patient_visits(session.patient.patient_id)
            q_lower_check = question.lower()
            for v in visits:
                v_no = str(v.get("Visit No.", "")).strip().lower()
                if v_no and v_no in q_lower_check:
                    # They explicitly mentioned this visit, make it sticky
                    from memory.visit_context import VisitContext
                    session.visit = VisitContext(
                        visit_id=v['Visit ID'],
                        patient_id=str(session.patient.patient_id),
                        visit_type=v['Visit Type'],
                        department=v['Department'],
                        visit_no=str(v.get('Visit No', v.get('Visit No.', ''))),
                        visit_date=str(v.get('Visit Date/Time', '')),
                    )
                    logger.info(f"Standalone query resolved sticky visit: {v['Visit ID']}")
                    break

        # 3. Handle Medical Report Request directly (catching typos and vague "show detail" requests)
        q_lower = question.lower().strip()
        is_report_request = "medical" in q_lower and any(word in q_lower for word in ["report", "record", "recourd", "file"])
        is_vague_detail_request = q_lower in ["show detail", "show details", "details", "detail"]
        if is_report_request or is_vague_detail_request:
            if not session.patient:
                return {
                    "answer": "Please specify a patient first before asking for a medical report.",
                    "sql": "",
                    "intent": "MEDICAL_REPORT",
                    "tables": [],
                    "patient": None
                }
                
            # Try to resolve a visit context for the medical report, but don't strictly require it
            resolver = VisitResolver()
            resolved_visit, msg = resolver.resolve_from_question(question, session.patient.patient_id)
            
            target_visit_id = None
            if resolved_visit:
                session.visit = resolved_visit
                target_visit_id = session.visit.visit_id
                logger.info(f"Intercepted full medical report request scoped to visit {target_visit_id}.")
            else:
                logger.info(f"Intercepted full medical report request for all visits of patient {session.patient.patient_id}.")
                
            from services.document_generator import DocumentGenerator
            try:
                gen = DocumentGenerator()
                record_data = gen.build_record_data(session.patient, target_visit_id=target_visit_id)
                md = gen.render_markdown(record_data)
                return {
                    "answer": md,
                    "sql": "Deterministic SQL queries executed for report.",
                    "intent": "MEDICAL_REPORT",
                    "tables": ["visit", "diagnosis", "vitals", "investigations"],
                    "patient": {
                        "name": session.patient.name,
                        "reg_no": session.patient.registration_no,
                        "id": session.patient.patient_id
                    } if session.patient else None
                }
            except Exception as e:
                logger.error(f"Error generating medical report in chat: {e}", exc_info=True)
                return {
                    "answer": "Failed to generate the comprehensive medical report.",
                    "sql": "",
                    "intent": "MEDICAL_REPORT",
                    "tables": [],
                    "patient": {
                        "name": session.patient.name,
                        "reg_no": session.patient.registration_no,
                        "id": session.patient.patient_id
                    } if session.patient else None
                }
                
        # 4. Detect Intents
        intents = self.intent_detector.detect_intent(question)

        # 4a. Handle ADD_RECORD (write path) — extract, resolve, ALWAYS show
        # an editable review form (never a dead-end error), require explicit
        # confirm (chat "confirm" OR the UI form's Confirm button). Nothing
        # is ever executed in this block — only session.pending_write is set.
        if "ADD_RECORD" in intents:
            from config.settings import ENABLE_WRITE_OPERATIONS, FAST_MODEL
            if not ENABLE_WRITE_OPERATIONS:
                answer = "Adding records isn't enabled yet. Please contact your admin."
                session.add_history(question, "", 0, "ADD_RECORD", answer)
                return {"answer": answer, "sql": "", "intent": "ADD_RECORD", "tables": []}

            if not session.patient:
                answer = "Please select a patient first before adding a record."
                session.add_history(question, "", 0, "ADD_RECORD", answer)
                return {"answer": answer, "sql": "", "intent": "ADD_RECORD", "tables": []}

            visit_auto_selected_note = ""
            if not session.visit:
                # Auto-pick the most recent visit instead of hard-blocking —
                # but this is NOT silent: it's clearly called out in the
                # response, and still shown again in the confirmation
                # summary below, so the doctor can catch a wrong pick
                # before anything is saved (same safety gate as before,
                # just with less upfront friction).
                from memory.visit_context import VisitContext
                visits = self.visit_resolver.fetch_patient_visits(session.patient.patient_id)
                if not visits:
                    answer = "Couldn't find any visits for this patient — please select/confirm a visit first."
                    session.add_history(question, "", 0, "ADD_RECORD", answer)
                    return {"answer": answer, "sql": "", "intent": "ADD_RECORD", "tables": []}
                latest = max(visits, key=lambda v: str(v.get("Visit Date/Time", "")))
                session.visit = VisitContext(
                    visit_id=latest['Visit ID'],
                    patient_id=str(session.patient.patient_id),
                    visit_type=latest.get('Visit Type', ''),
                    department=latest.get('Department', ''),
                    visit_no=str(latest.get('Visit No', '')),
                    visit_date=str(latest.get('Visit Date/Time', '')),
                )
                visit_auto_selected_note = f"📌 No visit was active, so I picked the most recent one — please double-check it below.\n\n"

            from llm import record_extractor
            from services import insert_service

            extracted = record_extractor.extract(question, self.answer_generator.llm, FAST_MODEL)
            entity_type = extracted["entity_type"]

            if not entity_type:
                answer = "I couldn't tell what you want to add. Try e.g. \"add prescription: paracetamol 500mg, twice a day, for 5 days\"."
                session.add_history(question, "", 0, "ADD_RECORD", answer)
                return {"answer": answer, "sql": "", "intent": "ADD_RECORD", "tables": []}

            # Resolve "lookup" fields (e.g. drug name -> drug_id). Unlike
            # before, a failed/ambiguous match no longer dead-ends the
            # request — we always continue to the review form, with fuzzy
            # suggestions attached as that field's dropdown options so the
            # doctor picks the right one there instead of retyping in chat.
            entity_schema = insert_service.get_form_schema(entity_type)
            resolved_values = dict(extracted["field_values"])
            field_options = {}  # key -> [{"id":..,"label":..}, ...] for lookup fields
            ai_alternative_note = None

            for f in entity_schema.get("fields", []):
                if f.get("type") != "lookup":
                    continue
                typed_name = resolved_values.get(f["key"])
                matched_id = None
                match = None
                if typed_name:
                    typed_name = str(typed_name)
                    # Query DB directly to bypass 2000 row limits
                    match = insert_service.find_exact_match(f["lookup_table"], f["lookup_id_col"], f["lookup_display_col"], typed_name.strip())
                    if match:
                        matched_id = match["id"]

                suggestions = []
                if match:
                    suggestions = [{"id": match["id"], "label": match["label"]}]
                elif typed_name:
                    # Fallback to fuzzy suggestions for the inline form so the doctor has options
                    fuzzy_matches = insert_service.find_lookup_matches(f["lookup_table"], f["lookup_id_col"], f["lookup_display_col"], typed_name.strip(), limit=5)
                    suggestions = [{"id": m["id"], "label": m["label"]} for m in fuzzy_matches]
                    if suggestions:
                        ai_alternative_note = f"⚠️ I couldn't find an exact match for **{typed_name}**. Please select the correct option from the dropdown below."
                
                field_options[f["key"]] = suggestions
                resolved_values[f["key"]] = matched_id  # None if unresolved — form will require a pick

            # Default any unmentioned datetime field to "now"
            import datetime as _dt
            for f in entity_schema.get("fields", []):
                if f.get("type") == "datetime" and not resolved_values.get(f["key"]):
                    resolved_values[f["key"]] = _dt.datetime.utcnow().isoformat()

            # Best-effort validation now (to decide what's still missing for
            # the form) — the real, authoritative validation always runs
            # again at actual insert time (chat "confirm" or the UI form's
            # submit), so a doctor editing values in the form can't bypass it.
            validation = insert_service.validate_only(entity_type, resolved_values)

            session.pending_write = {
                "entity_type": entity_type,
                "cleaned_field_values": validation["cleaned"] if validation["valid"] else {},
                "raw_field_values": resolved_values,
                "patient_id": session.patient.patient_id,
                "visit_id": session.visit.visit_id,
                "created_at": time.time(),
            }

            # Build the review-form payload for the UI (ui/app.py renders
            # this as an inline mini-form: selectbox for lookup fields
            # pre-filled with suggestions, text/number/date inputs for the
            # rest — all fields editable, not just the ambiguous one).
            form_fields = []
            for f in entity_schema.get("fields", []):
                form_fields.append({
                    "key": f["key"],
                    "label": f["label"],
                    "type": f.get("type", "text"),
                    "required": f.get("required", False),
                    "value": resolved_values.get(f["key"]),
                    "options": field_options.get(f["key"], []),
                    "min": f.get("min"),
                    "max": f.get("max"),
                })

            answer_lines = [visit_auto_selected_note.strip()] if visit_auto_selected_note else []
            if ai_alternative_note:
                answer_lines.append(ai_alternative_note)
            answer_lines.append(insert_service.build_confirmation_summary(entity_type, validation["cleaned"]) if validation["valid"]
                                 else "Please review and complete the fields below before confirming.")
            answer_lines.append(f"\n📋 **Visit:** {session.visit.display_label()}")
            answer_lines.append(f"👤 **Patient:** {session.patient.name} (Reg No: {session.patient.registration_no})")
            answer = "\n".join(answer_lines)
            session.add_history(question, "", 0, "ADD_RECORD", answer)

            return {
                "answer": answer,
                "sql": "",
                "intent": "ADD_RECORD",
                "tables": [],
                "add_record_form": {
                    "entity_type": entity_type,
                    "entity_label": entity_schema.get("label", entity_type),
                    "fields": form_fields,
                    "visit_label": session.visit.display_label(),
                    "patient_label": f"{session.patient.name} (Reg No: {session.patient.registration_no})",
                },
            }

        # 4. Handle Conversational & General Medical Bypass
        if len(intents) == 1 and intents[0] in ("CONVERSATIONAL", "GENERAL"):
            intent = intents[0]
            logger.info(f"Bypassing SQL Pipeline for {intent} intent.")
            plan = {"tables": []}
            
            # Check if this is an evaluative follow-up ("is it normal?", "in range?", "what is the use of")
            # that needs previous clinical data injected
            q_lower_eval = question.lower()

            # Domain-aware reverse scanning + evaluative-vs-explanatory
            # classification — LLM-based (see _classify_followup_context),
            # not hardcoded English keywords, so Hinglish/synonyms/typos
            # work the same as everything else in this app. Only calls the
            # LLM when there's actually history to disambiguate against.
            target_domain = None
            is_evaluative = False
            if session.history:
                from config.settings import FAST_MODEL
                target_domain, is_evaluative = _classify_followup_context(question, self.answer_generator.llm, FAST_MODEL)

            prev_clinical_data = None
            if session.history:
                for h in reversed(session.history):
                    if h.get("intent") in ("VITALS", "LAB", "PRESCRIPTION", "ALLERGY", "SURGERY"):
                        if target_domain and h.get("intent") != target_domain:
                            continue # skip if looking for a specific domain and it doesn't match
                            
                        # Truncate to max 1500 chars to prevent 413 payload too large errors
                        raw_ans = str(h.get("answer", ""))
                        if len(raw_ans) > 1500:
                            raw_ans = raw_ans[:1500] + "... [TRUNCATED]"
                        
                        # Prepend the domain name so LLM knows what it's evaluating
                        prev_clinical_data = f"Previous Context [{h.get('intent')}]:\n{raw_ans}"
                        logger.info(f"Found previous {h['intent']} data for conversational follow-up")
                        break
            
            if self.answer_generator:
                from database.connection_pool import get_connection
                hosp_info = ""
                try:
                    conn = get_connection()
                    cursor = conn.cursor(dictionary=True)
                    cursor.execute("SELECT display, address, phone1, email FROM fhir_hospital_mst LIMIT 1")
                    row = cursor.fetchone()
                    conn.close()
                    if row:
                        hosp_info = f"\nHospital Name: {row.get('display', '')}\nHospital Address: {row.get('address', '')}\nHospital Contact: {row.get('phone1', '')}, {row.get('email', '')}\n"
                except Exception:
                    pass

                base_ctx = session.get_context_summary()
                doc_ctx = f"\nLogged in Doctor Name: Dr. {doctor_id}\n"
                full_ctx = base_ctx + hosp_info + doc_ctx
                
                if prev_clinical_data:
                    if is_evaluative:
                        # Inject previous data into conversational prompt for evaluation/explanation
                        answer = self.answer_generator.generate_with_context(
                            question, prev_clinical_data, full_ctx
                        )
                    else:
                        augmented_context = f"{full_ctx}\n\nSpecifically referred data:\n{prev_clinical_data}"
                        answer = self.answer_generator.generate_conversational(question, augmented_context)
                else:
                    answer = self.answer_generator.generate_conversational(question, full_ctx)
            else:
                answer = "Hello! I am your AI assistant."
            sql = "N/A (Conversational)"
            rows_returned = 0
            retries = 0
            validation_errors = []
            
            session.add_history(question, sql, rows_returned, intent, answer=answer)
            execution_time = (time.time() - start_time) * 1000
            
            try:
                audit_logger.log_interaction(
                    session_id=session_id, doctor_id=doctor_id,
                    patient_id=session.patient.patient_id if session.patient else None,
                    intent=intent, question=question, sql=sql,
                    rows_returned=rows_returned, answer=answer,
                    execution_time_ms=execution_time, retries=retries,
                    validation_errors=validation_errors
                )
            except Exception as e:
                logger.warning(f"Audit log failed: {e}")
                
            return {
                "answer": answer,
                "sql": sql,
                "intent": intent,
                "tables": [],
                "patient": {
                    "name": session.patient.name,
                    "reg_no": session.patient.registration_no,
                    "id": session.patient.patient_id
                } if session.patient else None
            }

        # Handle data-fetching intents concurrently
        data_intents = [i for i in intents if i not in ("CONVERSATIONAL", "GENERAL")]
        if not data_intents:
            data_intents = intents # Fallback

        combined_answer_parts = []
        combined_sqls = []
        combined_tables = set()
        combined_raw_data = []
        total_rows_returned = 0
        all_validation_errors = []
        max_retries = 0
        
        def process_single_intent(intent: str):
            # Focus the query specifically on the current intent to prevent RAG/LLM confusion
            if len(data_intents) > 1:
                domain_name = intent.replace("_", " ").title()
                domain_specific_question = f"Show me the {domain_name} details for this patient."
            else:
                domain_specific_question = question

            # 4b. Plan Query (Fetch tables, examples, context)
            plan = self.query_planner.plan_query(domain_specific_question, intent, session)
            
            # 5. Generate, Validate, and Execute SQL (if sql_corrector available)
            sql = ""
            retries = 0
            validation_errors = []
            rows_returned = 0
            answer = ""
            raw_data = []
            
            if self.sql_corrector:
                try:
                    pipeline_result = self.sql_corrector.run_pipeline(domain_specific_question, plan)
                    sql = pipeline_result.get("sql", "")
                    retries = pipeline_result.get("retries", 0)
                    validation_errors = pipeline_result.get("final_errors", [])
                    res_dict = pipeline_result.get("result") or {}
                    
                    if res_dict.get("success"):
                        rows = res_dict.get("rows", [])
                        rows_returned = len(rows)
                        # If intent needs visit_no but AI didn't join it, enrich rows now
                        rows = self._enrich_with_visit_no(intent, rows)
                        # Map coded values natively using DB anchor joins (handled by SQL)
                        
                        if intent == "VITALS":
                            # ASC-sorted copy for graph (chronological trend)
                            raw_data = self._clean_raw_data(
                                self._sort_rows_by_date(rows, ascending=True)
                            )

                        # DESC-sorted copy for display (most recent first)
                        display_rows = self._sort_rows_by_date(rows, ascending=False)

                        if self.answer_generator:
                            domain_name = intent.replace("_", " ").title()
                            domain_question = f"For {domain_name}, " + question if len(data_intents) > 1 else question
                            answer = self.answer_generator.generate(domain_question, sql, display_rows, session.patient)
                            if len(data_intents) > 1 and answer and "no details were found" not in answer.lower():
                                answer = f"**{domain_name} Details:**\n{answer}"
                            elif len(data_intents) > 1:
                                answer = f"**{domain_name} Details:** No data found."
                        else:
                            answer = f"Query executed successfully returning {rows_returned} rows."
                    else:
                        rows_returned = 0
                        err_detail = res_dict.get("error", "Unknown error")
                        answer = f"I encountered an error querying the database for {intent}: {err_detail}"
                except Exception as pipeline_err:
                    logger.error(f"Pipeline execution error for {intent}: {pipeline_err}", exc_info=True)
                    rows_returned = 0
                    answer = f"I encountered an error processing your query for {intent}: {pipeline_err}"
            else:
                answer = "SQL execution pipeline unavailable."
                
            return {
                "intent": intent,
                "answer": answer,
                "sql": sql,
                "rows_returned": rows_returned,
                "retries": retries,
                "validation_errors": validation_errors,
                "tables": plan.get("tables", []),
                "raw_data": raw_data
            }

        # Execute sequentially with a small delay to prevent Cloud API 429 Concurrency/RPM bans
        results = []
        for idx, intent in enumerate(data_intents):
            if idx > 0:
                time.sleep(1.5) # Wait 1.5s between requests to respect free tier limits
            results.append(process_single_intent(intent))

        for res in results:
            if res["answer"]:
                combined_answer_parts.append(res["answer"])
            if res["sql"]:
                combined_sqls.append(f"-- {res['intent']} Query\n{res['sql']}")
            if res.get("raw_data"):
                combined_raw_data.extend(res["raw_data"])
            combined_tables.update(res["tables"])
            total_rows_returned += res["rows_returned"]
            all_validation_errors.extend(res["validation_errors"])
            max_retries = max(max_retries, res["retries"])
            
        final_answer = "\n\n".join(combined_answer_parts)
        final_sql = "\n\n".join(combined_sqls)
        final_intent = ",".join(data_intents)
        
        # 6. Update Session History
        session.add_history(question, final_sql, total_rows_returned, final_intent, answer=final_answer)
        
        execution_time = (time.time() - start_time) * 1000
        
        # 7. Audit Log
        try:
            audit_logger.log_interaction(
                session_id=session_id,
                doctor_id=doctor_id,
                patient_id=session.patient.patient_id if session.patient else None,
                intent=final_intent,
                question=question,
                sql=final_sql,
                rows_returned=total_rows_returned,
                answer=final_answer,
                execution_time_ms=execution_time,
                retries=max_retries,
                validation_errors=all_validation_errors
            )
        except Exception as e:
            logger.warning(f"Audit log failed: {e}")
        
        return {
            "answer": final_answer,
            "sql": final_sql,
            "intent": final_intent,
            "tables": list(combined_tables),
            "patient": {
                "name": session.patient.name,
                "reg_no": session.patient.registration_no,
                "id": session.patient.patient_id
            } if session.patient else None,
            "raw_data": combined_raw_data if combined_raw_data else None
        }

    # INTENTS that always need visit_no shown to the user
    _VISIT_NO_INTENTS = {"VITALS", "LAB", "PRESCRIPTION", "ALLERGY", "RADIOLOGY"}

    def _enrich_with_visit_no(self, intent: str, rows: list) -> list:
        """
        Guarantees visit_no is in the result rows for clinical intents.
        
        Strategy:
        If visitid/visit_id is already in the rows -> use it directly to lookup visitno.
        (The AI prompt enforces inclusion of visitid for clinical queries).
        """
        if intent not in self._VISIT_NO_INTENTS:
            return rows
        if not rows or not isinstance(rows[0], dict):
            return rows
        # Already has visit_no, nothing to do
        if "visit_no" in rows[0] or "visitno" in rows[0]:
            return rows

        try:
            conn = get_connection()
            cur = conn.cursor(dictionary=True)

            visit_id_col = next((c for c in rows[0] if c.lower() in ("visitid", "visit_id")), None)
            if visit_id_col:
                visit_ids = list({r[visit_id_col] for r in rows if r.get(visit_id_col)})
                if visit_ids:
                    placeholders = ",".join(["%s"] * len(visit_ids))
                    cur.execute(
                        f"SELECT id, visitno FROM fhir_visit_mst WHERE id IN ({placeholders})",
                        visit_ids
                    )
                    visit_map = {row["id"]: row["visitno"] for row in cur.fetchall()}
                    for i, row in enumerate(rows):
                        vid = row.get(visit_id_col)
                        vno = visit_map.get(vid, "")
                        rows[i] = {"visit_no": vno, **row}  # visit_no goes first
                    logger.info(f"visit_no enrichment done for {len(rows)} rows")
                    
            cur.close()
            conn.close()

        except Exception as e:
            logger.warning(f"visit_no enrichment failed: {e}")

        return rows

    def _clean_raw_data(self, rows: list) -> list:
        """Strips out audit and internal columns from raw DB rows."""
        if not rows:
            return []
        cleaned_rows = []
        audit_prefixes = ("inserted", "updated", "cancelled", "macid", "ipaddress")
        for row in rows:
            if isinstance(row, dict):
                clean_r = {}
                for k, v in row.items():
                    if v is None or v == "" or str(v).lower() in ("null", "none"):
                        continue
                    if any(k.lower().startswith(p) or k.lower().endswith(p) for p in audit_prefixes):
                        continue
                    clean_r[k] = v
                cleaned_rows.append(clean_r)
            else:
                cleaned_rows.append(row)
        return cleaned_rows



    def _sort_rows_by_date(self, rows: list, ascending: bool = False) -> list:
        """Returns a SORTED COPY of rows by the first date/time column found.
        
        Does NOT mutate the original list — critical for dual-sort:
        - ascending=True  -> for graph/chart (chronological trend)
        - ascending=False -> for display table (most recent first)
        """
        if not rows or not isinstance(rows[0], dict):
            return list(rows)  # return copy
        
        # Find the first date/time column
        date_col = None
        date_keywords = ("date", "time", "datetime", "dttime", "createdon", "insertedon")
        for k in rows[0].keys():
            if any(kw in k.lower() for kw in date_keywords):
                date_col = k
                break
        
        if not date_col:
            return list(rows)  # no date column found, return copy as-is
        
        try:
            sorted_rows = sorted(
                rows,
                key=lambda r: str(r.get(date_col, "")),
                reverse=not ascending
            )
            return sorted_rows
        except Exception as e:
            logger.warning(f"Date sorting failed: {e}")
            return list(rows)
