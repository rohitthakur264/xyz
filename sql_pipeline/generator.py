import re
import ollama
from config.settings import SQL_MODEL, LLM_TEMPERATURE
from config.prompts import MASTER_SYSTEM_PROMPT
from sql_pipeline.validator import validate_sql
from sql_pipeline.executor import execute_sql

def _extract_sql(raw_text):
    """Strip markdown fences and pull out just the SQL statement,
    even if the model added stray prose before/after it."""
    text = raw_text.strip()
    text = re.sub(r"^```sql", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^```", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    match = re.search(r"(SELECT\b.*)", text, re.IGNORECASE | re.DOTALL)
    if match:
        text = match.group(1).strip()
        # cut off at the first semicolon or trailing prose sentence, if present
        if ";" in text:
            text = text.split(";")[0].strip() + ";"
    return text

def generate_and_execute_sql(question, retrieved_schema, active_patient=None, max_retries=2):
    schema_context = ""
    for table_name, info in retrieved_schema.items():
        cols = ", ".join([f"{c['column_name']} ({c['data_type']})" for c in info['columns']])
        fks = ", ".join([f"{f['column_name']} -> {f['referenced_table']}.{f['referenced_column']}" for f in info['fks']])
        schema_context += f"Table: {table_name}\nColumns: {cols}\n"
        if fks:
            schema_context += f"Foreign Keys: {fks}\n"
        schema_context += "\n"

    system_prompt = MASTER_SYSTEM_PROMPT + "\n\n=== TASK: SQL GENERATION ===\n"
    system_prompt += (
        "Write a single valid SELECT query to answer the user's question based strictly on the provided schema.\n"
        "Return ONLY the raw SQL query. No markdown formatting, no explanations, no commentary — SQL only.\n"
        "If you hit an 'Illegal mix of collations' error, add COLLATE utf8mb4_unicode_ci to the compared columns."
    )

    if active_patient:
        patient_id = active_patient['id']
        reg_no = active_patient.get('registration_no', '')
        system_prompt += (
            f"\nActive patient context: patient internal ID is {patient_id} (integer field `patientid` or `id`), "
            f"registration_no is '{reg_no}'.\n"
            "\n=== CRITICAL SCHEMA RULES (verified against live DB) ===\n"
            f"0. STRICT RULE: DO NOT INVENT TABLES. Only use the exact table names provided in the schema below.\n"
            f"1. PATIENT PROFILE: SELECT * FROM fhir_patient_mst WHERE id = {patient_id}\n"
            f"2. VISIT JOIN: fhir_visit_mst PK is 'id' (NOT visit_id, NOT visitid). Always filter by `patientid = {patient_id}`. DO NOT use `oldregistration_no`.\n"
            f"3. VITALS: Use fhir_patient_vitals WHERE patientid = {patient_id} "
            f"(its visit link column is 'visit_id', NOT 'visitid'). "
            f"Alternative: fhir_tprbp_dtl has NO patientid — must join: "
            f"fhir_tprbp_dtl.visit_id = fhir_visit_mst.id WHERE fhir_visit_mst.patientid = {patient_id}\n"
            f"4. BILLING: SELECT * FROM fhir_bill_mst WHERE registration_no = '{reg_no}' "
            f"(direct — no join needed). OR join: fhir_bill_mst.visit_id = fhir_visit_mst.id WHERE patientid={patient_id}\n"
            f"5. PRESCRIPTIONS / DRUGS: Use fhir_order_mst WHERE ordpatientid = {patient_id} "
            f"(note: column is ordpatientid, NOT patientid). "
            f"For drug names: JOIN fhir_order_dtl ON order_id = ordid, "
            f"then JOIN fhir_drug_mst ON fhir_order_dtl.service_id = fhir_drug_mst.id. "
            f"Written prescriptions: fhir_prescription_dtl, JOIN fhir_drug_mst ON itemid = id.\n"
            f"6. ALLERGIES: SELECT * FROM fhir_patient_allergy WHERE patientid = {patient_id}\n"
            f"7. SURGERY/OT: SELECT * FROM fhir_ot_scheduling_mst WHERE patientid = {patient_id}\n"
            f"8. ORDERS: fhir_order_mst uses ordpatientid = {patient_id} and ordvisitid (NOT patientid/visitid).\n"
            f"9. SECONDARY TABLES always filter by patientid = {patient_id} (integer). "
            f"NEVER filter by registration_no string unless the table explicitly has that column "
            f"(only fhir_bill_mst and fhir_patient_mst do).\n"
        )

    attempts_debug = []
    previous_sql = None
    previous_error = None

    allowed_tables = list(retrieved_schema.keys())
    for attempt in range(max_retries + 1):
        user_content = f"Schema:\n{schema_context}\nQuestion: {question}"
        if previous_sql:
            user_content += (
                f"\n\nYour previous attempt was:\n{previous_sql}\n"
                f"It failed with this error:\n{previous_error}\n"
                f"CRITICAL FIX REQUIRED: You MUST use ONLY the following tables: {allowed_tables}. "
                f"Do not invent new tables (e.g., fhir_billing_details, fhir_vitals_dtl). "
                f"Check the exact column names in the schema above before using them. "
                f"Write a corrected query. Return ONLY the raw SQL query."
            )

        # Fresh, isolated messages every attempt — no accumulating conversation.
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            response = ollama.chat(
                model=SQL_MODEL,
                messages=messages,
                options={'temperature': LLM_TEMPERATURE}
            )
            raw_sql = _extract_sql(response['message']['content'])

            valid_sql, val_error = validate_sql(raw_sql, retrieved_schema, active_patient=active_patient)
            if val_error:
                attempts_debug.append({"attempt": attempt + 1, "sql": raw_sql, "error": val_error, "type": "validation"})
                if val_error.startswith("NEEDS_PATIENT:"):
                    return None, None, None, val_error, attempts_debug
                    
                print(f"[Attempt {attempt+1}] Validation failed: {val_error}")
                previous_sql, previous_error = raw_sql, val_error
                continue

            columns, rows, exec_error = execute_sql(valid_sql)
            if exec_error:
                print(f"[Attempt {attempt+1}] Execution failed: {exec_error}")
                attempts_debug.append({"attempt": attempt + 1, "sql": valid_sql, "error": exec_error, "type": "execution"})
                previous_sql, previous_error = valid_sql, exec_error
                continue

            attempts_debug.append({"attempt": attempt + 1, "sql": valid_sql, "error": None, "type": "success"})
            return valid_sql, rows, columns, None, attempts_debug

        except Exception as e:
            attempts_debug.append({"attempt": attempt + 1, "sql": None, "error": f"LLM error: {e}", "type": "exception"})
            return None, None, None, f"LLM error: {e}", attempts_debug

    return None, None, None, "Failed to generate valid SQL after maximum retries.", attempts_debug