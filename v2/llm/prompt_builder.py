SYSTEM_PROMPT = """You are an expert EMR database query generator.
Your ONLY job is to output a syntactically correct MySQL query.
Do NOT output any markdown, markdown code blocks (```sql), explanations, or conversational text.
ONLY output the raw SQL string starting with SELECT."""

BUSINESS_RULES = """### Business Rules
- `registration_no` is the patient registration string (e.g. '165881') in `fhir_patient_mst`.
- `patientid` in clinical/transactional tables (e.g., `fhir_visit_mst`, `fhir_bill_mst`, `fhir_order_mst`) is the numeric Primary Key `id` from `fhir_patient_mst` (e.g., `id = 180267`), NOT `registration_no`!
- NEVER set `patientid = registration_no`. For example, DO NOT write `patientid = 165881` if 165881 is the registration_no. Instead write `patientid = 180267` (using Current Patient ID), OR `JOIN fhir_patient_mst ON fhir_patient_mst.id = fhir_visit_mst.patientid WHERE fhir_patient_mst.registration_no = '165881'`.
- Only join tables that are provided in the Schema section.
- NEVER use columns that are not explicitly listed in the Schema.
- Pay attention to the Session Context. If an Active Patient is loaded, automatically inject `patientid = <Current Patient ID>` into the WHERE clause for transactional tables."""

def build_schema_section(tables: list, full_schema_cache: dict) -> str:
    """Renders the allowed tables and their columns into the prompt."""
    schema_str = "### Allowed Schema\n"
    for t in tables:
        if t in full_schema_cache:
            info = full_schema_cache[t]
            cols = [f"{c['column_name']} ({c['data_type']})" for c in info['columns']]
            schema_str += f"- Table `{t}`: {', '.join(cols)}\n"
    return schema_str

def build_examples_section(examples: list) -> str:
    if not examples:
        return ""
    ex_str = "### Examples (DO NOT COPY DIRECTLY IF THE QUESTION DIFFERS)\n"
    for i, ex in enumerate(examples):
        ex_str += f"Q: {ex['question']}\nSQL: {ex['sql']}\n\n"
    return ex_str

def build_context_section(context_str: str) -> str:
    if not context_str or "No patient" in context_str:
        return ""
    return f"### Active Session Context\n{context_str}\n"

def build_error_correction_section(errors: list) -> str:
    if not errors:
        return ""
    err_str = "### CRITICAL: PREVIOUS SQL FAILED\nYour last attempt failed with the following errors:\n"
    for e in errors:
        err_str += f"- {e}\n"
    err_str += "Fix these errors and produce a corrected SQL query.\n"
    return err_str
