SYSTEM_PROMPT = """You are an expert EMR database query generator.
Your ONLY job is to output a syntactically correct MySQL query.
Do NOT output any markdown, markdown code blocks (```sql), explanations, or conversational text.
ONLY output the raw SQL string starting with SELECT.
CRITICAL RULES:
1. NEVER use SELECT * or select massive numbers of columns. Keep the selected columns strictly relevant and minimal (max 10-15 columns) to prevent token overflow.
2. DO NOT REPEAT COLUMNS. Do not output the same column name multiple times in the SELECT list.
3. NEVER hallucinate columns. ONLY use columns explicitly listed in the 'Allowed Schema'. If you are unsure, do not include the column.
4. ONLY output the SQL query. No other text."""

import json
import os

def build_business_rules(full_schema_cache: dict, intent: str = None) -> str:
    """Build the business rules, injecting master-table names derived from the schema.

    Table names and intent rules are never hardcoded here; they are discovered from the live schema
    and the intent config.
    """
    from database.schema_anchors import find_anchor_tables, PATIENT_FK_CANDIDATES

    a = find_anchor_tables(full_schema_cache)
    patient = a.get("patient") or "fhir_patient_mst"
    visit = a.get("visit") or "fhir_visit_mst"
    bill = a.get("bill") or "fhir_bill_mst"
    order = a.get("order") or "fhir_order_mst"

    # Dynamically extract patient table schema details
    patient_pk = "id"
    patient_reg_col = "registration_no"
    if patient in full_schema_cache:
        patient_info = full_schema_cache[patient]
        patient_pk = patient_info.get("primary_key") or "id"
        cols = [c["column_name"] for c in patient_info.get("columns", [])]
        for col in ["registration_no", "mrn", "patient_no", "reg_no"]:
            if col in cols:
                patient_reg_col = col
                break

    # Dynamically extract visit table schema details
    visit_pk = "id"
    visit_no_col = "visitno"
    if visit in full_schema_cache:
        visit_info = full_schema_cache[visit]
        visit_pk = visit_info.get("primary_key") or "id"
        v_cols = [c["column_name"] for c in visit_info.get("columns", [])]
        for col in ["visitno", "visit_no"]:
            if col in v_cols:
                visit_no_col = col
                break
                
    # Detect actual FK column used in a real transactional table instead of assuming
    patient_fk = "patientid"  # last-resort fallback only
    if visit in full_schema_cache:
        visit_cols = [c["column_name"] for c in full_schema_cache[visit].get("columns", [])]
        for candidate in PATIENT_FK_CANDIDATES:
            if candidate in visit_cols:
                patient_fk = candidate
                break

    base_rules = f"""### Business Rules
- `{patient_reg_col}` is the patient registration string (e.g. '165881') in `{patient}`.
- `{patient_fk}` in clinical/transactional tables (e.g., `{visit}`, `{order}`) is the numeric Primary Key `{patient_pk}` from `{patient}` (e.g., `{patient_pk} = 180267`), NOT `{patient_reg_col}`!
- NEVER set `{patient_fk} = {patient_reg_col}`. For example, DO NOT write `{patient_fk} = 165881` if 165881 is the {patient_reg_col}. Instead write `{patient_fk} = 180267` (using Current Patient ID), OR `JOIN {patient} ON {patient}.{patient_pk} = <transactional>.{patient_fk} WHERE {patient}.{patient_reg_col} = '165881'`.
- Pay attention to the Session Context. If an Active Patient is loaded, automatically inject `{patient_fk} = <Current Patient ID>` or `{patient_reg_col} = <Patient Reg No>` into the WHERE clause.
- If given an Active Visit Context, filter the relevant table using its visit-link column directly, UNLESS the question explicitly asks about visit history, all visits, or previous/other visits — in that case, scope by patient only, not by the active visit.
- SEARCHING PATIENTS: If the user provides a registration number or name in their question, you MUST include a `WHERE` clause filtering by `{patient_reg_col}` or name. Do NOT write queries without a WHERE clause for patient search!
- STRICT SCHEMA ADHERENCE: You must NEVER use a table name or column name that is not explicitly listed in the 'Allowed Schema' section. Do NOT invent table names (e.g., 'the operation table') or columns like `testname`, `prescriptionid`, `deactive`, `type_id`, `insertedmacname`, etc. if they are not in the schema list. ONLY use exact table and column names from the schema list.
- CLINICAL QUERIES (Vitals, Labs, Prescriptions, Allergies, Surgery): You MUST include a visit foreign key column in your SELECT statement if it exists in the tables you are querying. Always attempt to JOIN `{visit}` and SELECT `{visit}.{visit_no_col}` so the doctor knows which visit the data belongs to.
- LAB QUERIES: If querying lab results, you MUST select `Critical` column so the doctor can evaluate the results. Do NOT select paramnormalrange, paramlow, or paramhigh.
- LAB ORDERS: When querying lab orders, use `fhir_order_mst` and `fhir_order_dtl`. DO NOT invent `fhir_order_detail`. The primary key is `ordid`, NOT `orderid`. Date column is `orddatetime`. To get the test name, JOIN `fhir_lab_test_mst` ON `fhir_order_dtl.serviceid = fhir_lab_test_mst.serviceid`.
- PATIENT DETAILS: Select only the exact columns from the schema. Do NOT assume columns like `patient_name` or `address` exist if they are not listed. However, if the user asks for patient demographics, name, or details, you MUST use `CONCAT(first_name, ' ', last_name) AS 'Full Name'` and `CONCAT(r_firstname, ' ', r_familyname) AS 'Full Name (Arabic)'` instead of selecting `first_name` and `arbname` individually.
- VISIT DETAILS: When querying visit details, you MUST use `LEFT JOIN` for optional related tables like ward, room, and bed (e.g. `LEFT JOIN fhir_ward_mst`, `LEFT JOIN fhir_room_mst`, `LEFT JOIN fhir_bed_mst`). If you use an INNER JOIN, you will accidentally filter out all OPD visits!
- ALIASING JOINS: When using table aliases, make sure you use the exact column names specified in the 'Mandatory JOIN path'. Do not alter the column names when they alias them (e.g., if the join path says `fhir_prescription_dtl.preid`, you must use `pd.preid`, NOT `pd.prescriptionid`).
- AMBIGUOUS COLUMNS: When joining multiple tables, you MUST ALWAYS prefix every column name with its table name or alias in the SELECT, WHERE, and ORDER BY clauses (e.g., SELECT `{patient}.display`, `{patient}.id` instead of just `display`, `id`) to prevent 'ambiguous column' MySQL errors.
- CODED VALUE LOOKUPS: When the query involves columns like `Gender`, `nationality`, or other numeric codes that reference a lookup/master table (e.g., `fhir_gender_mst`, `fhir_nationality_mst`), you MUST JOIN to the lookup table and SELECT its `display` column instead of the raw numeric code. For example: `JOIN fhir_gender_mst g ON {patient}.Gender = g.id` and then SELECT `g.display AS gender`.
- EVALUATIVE QUESTIONS: If the user asks an evaluative question (e.g., "are the vitals normal?", "is the lab test in range?"), DO NOT try to calculate the status or join range tables in SQL. Just SELECT the raw data (e.g., `systolic`, `diastolic`, `result`). The application logic will handle the range evaluation.
- ALLERGIES: Query allergies from `fhir_op_nurse_assessment_dtl` (alias n). To filter by patient, join `fhir_patient_mst` (alias p) `ON n.patientid = p.patientid` (or filter by `n.patientid = <Patient ID>`), and join `{visit}` (alias v) `ON n.visitid = v.visit_id` to select `{visit}.{visit_no_col}`. You MUST append `COLLATE utf8mb4_unicode_ci` when joining allergy master tables on code (e.g., `n.allergy COLLATE utf8mb4_unicode_ci = am.code`) to avoid collation mismatch errors. SELECT `COALESCE(am.display, af.display, a.display, n.allergy) AS allergy_name`, `n.reaction`, `v.visitno`.
- SURGERY: When querying operations or surgeries, you MUST join from `fhir_ot_scheduling_mst` (alias ot) to `fhir_ot_schedulling_dtl` (alias dtl) `ON ot.id = dtl.schid`, and then join `fhir_service_mst` (alias srv) `ON dtl.procedureid = srv.id`. To filter by patient, you MUST join `fhir_visit_mst` (alias v) `ON ot.visitid = v.visit_id` and then `fhir_patient_mst` (alias p) `ON v.patientid = p.patientid`. SELECT `srv.display AS operation_name`. NEVER join `fhir_ot_scheduling_mst` and `fhir_patient_mst` directly. DO NOT invent columns!
- PRESCRIPTIONS: You MUST filter prescriptions by the patient's numeric ID (e.g. `pm.patientid = <Patient ID>`). NEVER filter by `pm.code = @registration_no`. Join `fhir_prescription_dtl` ON `pm.id = dt.hm_id` (or correct schema key). SELECT columns in this sequence: drug name, dosage, frequency, duration, quantity, notes, visit no, prescription date.
- BILLING: When querying bills, you MUST ONLY SELECT these exact columns: bill no, bill date, visit no, gross amount, net amount, and due amount. DO NOT select discount, concession, surcharge, write-off, round-off, or bill type.
- DEPARTMENTS: When selecting departmentid from visits, you MUST join `fhir_department_mst` (e.g., `JOIN fhir_department_mst dept ON v.departmentid = dept.id`) and select `dept.display AS department` so the ACTUAL department name appears. DO NOT alias visit type as department.
- RADIOLOGY: Query radiology results from `fhir_rad_imgservices` and related detail tables (`fhir_rad_imgservices_dtl`), NOT just `fhir_encounter`. Use `patientid` to filter. You MUST ONLY SELECT these exact columns in this sequence: ID, Visit No, Visit Date, Service DisplayResult, and Is Critical. DO NOT select Report Format ID, Department ID, or Is Active.
- DISCHARGE SUMMARY: When querying discharge summaries, query `fhir_dischargesummary_mst` (alias ds) and filter by `ds.patientid`. DO NOT join irrelevant tables.
- RESULT ORDERING: Always add `ORDER BY` with date/time columns in **DESC** order (most recent first) unless the user specifically asks for oldest first. Use the most relevant date column available (e.g., `billdate`, `reading_datetime`, `visitdate`, `insertedon`, `resultdttime`)."""

    return base_rules

def build_schema_section(tables: list, full_schema_cache: dict) -> str:
    """Renders the allowed tables and their columns into the prompt, filtering noisy audit columns."""
    from config.settings import IGNORE_COLUMNS, AUDIT_PREFIXES
    ignore_set = {c.strip().lower() for c in IGNORE_COLUMNS if c.strip()}
    audit_prefixes = tuple(p.strip().lower() for p in AUDIT_PREFIXES if p.strip())

    schema_str = "### Allowed Schema\n"
    for t in tables:
        if t in full_schema_cache:
            info = full_schema_cache[t]
            filtered_cols = []
            for c in info.get('columns', []):
                c_name = c['column_name']
                c_lower = c_name.lower()
                if c_lower in ignore_set or any(c_lower.startswith(pref) for pref in audit_prefixes):
                    continue
                filtered_cols.append(f"{c_name} ({c['data_type']})")
            schema_str += f"- Table `{t}`: {', '.join(filtered_cols)}\n"
    return schema_str

def build_joins_section(joins: list) -> str:
    """Render schema-derived JOIN hints so the model does not invent join columns."""
    if not joins:
        return ""
    j_str = "### Mandatory JOIN path\n"
    j_str += "These JOIN conditions are derived from the verified schema. If you need to connect the listed tables, "
    j_str += "you MUST use exactly these ON clauses. Do NOT invent other join columns.\n"
    for j in joins:
        j_str += f"- {j}\n"
    return j_str


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
    return f"### Active Session Context\n{context_str}\n\nCRITICAL INSTRUCTION: You MUST use the patient ID and registration number from THIS Active Session Context in your SQL WHERE clause. DO NOT blindly copy patient IDs or registration numbers like '166637' from the Examples section. If you copy an ID from the examples instead of the Active Session Context, the query will return data for the WRONG patient!\n"

def build_error_correction_section(errors: list) -> str:
    if not errors:
        return ""
    err_str = "### CRITICAL: PREVIOUS SQL FAILED\nYour last attempt failed with the following errors:\n"
    for e in errors:
        err_str += f"- {str(e)[:300]}\n"
    err_str += "Fix these errors and produce a corrected SQL query.\n"
    return err_str
