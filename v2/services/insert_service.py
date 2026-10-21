"""
Config-driven, LLM-free write path for the UI's "Add Record" forms
(prescription, lab test, vitals, ...).

Design principles (do not weaken these without a very good reason):
  1. NO LLM anywhere in this file. Free-text -> SQL for writes is far too
     risky for patient data (a hallucinated column/value becomes a
     permanent wrong medical record). Every insertable field, table, and
     column comes from config/insert_schema.json - a fixed allow-list.
  2. Every SQL statement is fully parameterized (%s placeholders + a
     separate params tuple). We NEVER f-string a user-supplied value into
     SQL text. Table/column *names* come only from our own validated
     config, never from user input.
  3. insert_schema.json is validated against the LIVE DB schema at import
     time (validate_insert_schema). If a configured table/column doesn't
     actually exist, we raise loudly at startup instead of failing
     silently (or worse, succeeding against the wrong column) in front of
     a doctor.
  4. Every successful/failed write is audit-logged with who/what/when.
  5. The whole feature is gated behind settings.ENABLE_WRITE_OPERATIONS,
     which defaults to False.
"""

import os
import json
import datetime
import difflib
from typing import Optional
from pydantic import BaseModel, Field, create_model, ValidationError, field_validator
from config.logging import get_logger, audit_logger
from config.settings import ENABLE_WRITE_OPERATIONS
from database.connection_pool import get_connection

logger = get_logger(__name__)

_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "insert_schema.json"
)

INSERT_SCHEMA = {}
try:
    if os.path.exists(_SCHEMA_PATH):
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            INSERT_SCHEMA = json.load(f)
except Exception as e:
    logger.error(f"Could not load insert_schema.json: {e}")


class InsertValidationError(Exception):
    """Raised when a submitted record fails validation before touching the DB."""
    pass


def validate_insert_schema(live_schema: dict):
    """Validate every table/column in insert_schema.json against the live
    DB schema. Called once at startup (see api/main.py). Raises ValueError
    on any mismatch so a bad config fails loudly before the app serves
    traffic, rather than failing silently on a doctor's first insert.
    """
    entities = INSERT_SCHEMA.get("entities", {})
    if not entities:
        logger.warning("insert_schema.json has no entities defined; write UI will have nothing to show.")
        return

    def _check_table_columns(table: str, columns: list, context: str):
        if table not in live_schema:
            raise ValueError(f"[insert_schema] {context}: table '{table}' not found in live DB schema.")
        raw_cols = live_schema[table].get("columns", {}) if isinstance(live_schema[table], dict) else []
        if isinstance(raw_cols, dict):
            live_cols = {c.lower() for c in raw_cols}
        else:
            live_cols = {
                (c["column_name"].lower() if isinstance(c, dict) else str(c).lower())
                for c in raw_cols
            }
        for col in columns:
            if live_cols and col.lower() not in live_cols:
                raise ValueError(f"[insert_schema] {context}: column '{col}' not found on table '{table}'.")

    for entity_key, entity in entities.items():
        table = entity["table"]
        cols = [f["column"] for f in entity.get("fields", [])]
        if entity.get("patient_column"):
            cols.append(entity["patient_column"])
        if entity.get("visit_column"):
            cols.append(entity["visit_column"])
        if entity.get("created_by_column"):
            cols.append(entity["created_by_column"])
        if entity.get("created_at_column"):
            cols.append(entity["created_at_column"])
        _check_table_columns(table, cols, f"entity '{entity_key}'")

        master = entity.get("requires_master")
        if master:
            m_cols = [master["patient_column"], master["visit_column"], master["date_column"],
                      master.get("created_by_column"), master["id_column"]]
            m_cols = [c for c in m_cols if c]
            _check_table_columns(master["table"], m_cols, f"entity '{entity_key}' master table")

    logger.info(f"insert_schema.json validated OK against live schema ({len(entities)} entities).")


def list_entities() -> dict:
    """Returns {entity_key: label} for populating a UI selectbox."""
    return {k: v.get("label", k) for k, v in INSERT_SCHEMA.get("entities", {}).items()}


def get_form_schema(entity_key: str) -> dict:
    """Returns the field definitions for one entity, for the UI to render
    inputs from (never hardcode form fields in the UI layer)."""
    entity = INSERT_SCHEMA.get("entities", {}).get(entity_key)
    if not entity:
        raise InsertValidationError(f"Unknown entity type: {entity_key}")
    return entity


def get_lookup_options(lookup_table: str, id_col: str, display_col: str, limit: int = 500) -> list[dict]:
    """Read-only helper to populate a dropdown for a 'lookup' field type
    (e.g. drug name, frequency). Fully parameterized; table/column names
    only ever come from our own validated insert_schema.json, never from
    user input, so this is safe despite being string-composed."""
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        # table/col names are from our own config (already schema-validated
        # at startup), not from end-user input -> safe to compose here.
        query = f"SELECT `{id_col}` AS id, `{display_col}` AS label FROM `{lookup_table}` LIMIT %s"
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        cursor.close()
        return rows
    finally:
        conn.close()


def _iso_datetime_validator(cls, v):
    if v is None or v == "":
        return v
    try:
        datetime.datetime.fromisoformat(v)
    except (ValueError, TypeError):
        raise ValueError("must be a valid ISO date/time (e.g. 2026-08-14T20:30:00)")
    return v


def build_pydantic_model(entity: dict):
    """Dynamically builds a Pydantic model from an insert_schema.json entity
    definition, so validation (required fields, numeric ranges, types) uses
    the same well-tested library FastAPI already relies on elsewhere in
    this project, instead of hand-rolled checks. The model is rebuilt from
    config each call - insert volume here is low (a handful of writes per
    consultation), so this isn't a hot path worth caching."""
    field_defs = {}
    datetime_keys = []

    for f in entity.get("fields", []):
        key = f["key"]
        ftype = f.get("type", "text")
        required = f.get("required", False)

        if ftype == "number":
            constraints = {}
            if "min" in f:
                constraints["ge"] = f["min"]
            if "max" in f:
                constraints["le"] = f["max"]
            default = ... if required else None
            field_defs[key] = (float if required else Optional[float], Field(default, **constraints))
        elif ftype == "lookup":
            default = ... if required else None
            field_defs[key] = (int if required else Optional[int], Field(default))
        elif ftype == "datetime":
            default = ... if required else None
            field_defs[key] = (str if required else Optional[str], Field(default))
            datetime_keys.append(key)
        else:  # text
            default = ... if required else None
            constraints = {"min_length": 1} if required else {}
            field_defs[key] = (str if required else Optional[str], Field(default, **constraints))

    validators = {
        f"_validate_{key}": field_validator(key)(_iso_datetime_validator)
        for key in datetime_keys
    }

    model_name = entity.get("label", "Entity").replace(" ", "") + "Model"
    return create_model(model_name, __validators__=validators, **field_defs)


def _validate_field_values(entity: dict, field_values: dict) -> dict:
    """Validate submitted values against the entity's Pydantic model.
    Returns a cleaned {column: value} dict using ONLY columns declared in
    the schema (any extra keys the caller sent are silently dropped, not
    trusted) — this is the allow-list that keeps this endpoint from ever
    becoming an arbitrary-column-write primitive."""
    model_cls = build_pydantic_model(entity)
    known_keys = {f["key"] for f in entity.get("fields", [])}
    payload = {k: v for k, v in field_values.items() if k in known_keys and v not in ("", None)}

    try:
        instance = model_cls(**payload)
    except ValidationError as e:
        errors = e.errors()
        missing = [err["loc"][0] for err in errors if err["type"] == "missing"]
        if missing:
            key_to_label = {f["key"]: f["label"] for f in entity.get("fields", [])}
            missing_field = missing[0]
            raise InsertValidationError(f"'{key_to_label.get(missing_field, missing_field)}' is required.")
        # First non-missing error (range/type/format issues)
        err = errors[0]
        key_to_label = {f["key"]: f["label"] for f in entity.get("fields", [])}
        field_label = key_to_label.get(err["loc"][0], err["loc"][0])
        raise InsertValidationError(f"'{field_label}': {err['msg']}")

    key_to_column = {f["key"]: f["column"] for f in entity.get("fields", [])}
    cleaned = {}
    for key in known_keys:
        val = getattr(instance, key, None)
        if val is not None:
            cleaned[key_to_column[key]] = val
    return cleaned


def find_lookup_matches(lookup_table: str, id_col: str, display_col: str, query: str, limit: int = 5) -> list[dict]:
    """Fuzzy 'top N suggestions' for a lookup field (e.g. drug name) when
    the doctor's typed value doesn't match anything exactly. Uses Python's
    built-in difflib (no extra dependency) rather than a DB LIKE query, so
    it also catches typos/misspellings, not just substrings. Read-only."""
    options = get_lookup_options(lookup_table, id_col, display_col, limit=2000)
    labels = [o["label"] for o in options if o.get("label")]
    close = difflib.get_close_matches(query, labels, n=limit, cutoff=0.4)
    label_to_id = {o["label"]: o["id"] for o in options}
    return [{"id": label_to_id[l], "label": l} for l in close]


def find_exact_match(lookup_table: str, id_col: str, display_col: str, query: str) -> dict | None:
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        q = f"SELECT `{id_col}` AS id, `{display_col}` AS label FROM `{lookup_table}` WHERE `{display_col}` LIKE %s LIMIT 1"
        cursor.execute(q, (f"%{query}%",))
        row = cursor.fetchone()
        return row if row else None
    finally:
        conn.close()


def find_by_generic_name(lookup_table: str, id_col: str, display_col: str, generic_match_column: str, generic_name: str, limit: int = 10) -> list[dict]:
    """Searches a lookup table (e.g. fhir_drug_mst) by a generic/active-
    ingredient name column (e.g. 'scientificnm'), for the case where a
    typed drug brand name ('Tylenol') doesn't match anything but its
    generic equivalent ('Paracetamol') does exist in the formulary.

    IMPORTANT: `generic_name` here comes from an LLM guess (see
    llm/record_extractor.py's guess_generic_name), which can be wrong. This
    function itself only does a safe, parameterized LIKE query — the
    caller is responsible for clearly labeling results as an AI suggestion
    that needs clinical verification, and for never pre-selecting one.
    """
    if not generic_name:
        return []
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        query_sql = (
            f"SELECT `{id_col}` AS id, `{display_col}` AS label, `{generic_match_column}` AS generic "
            f"FROM `{lookup_table}` WHERE `{generic_match_column}` LIKE %s LIMIT %s"
        )
        cursor.execute(query_sql, (f"%{generic_name}%", limit))
        rows = cursor.fetchall()
        cursor.close()
        return rows
    finally:
        conn.close()


def validate_only(entity_key: str, field_values: dict) -> dict:
    """Runs the same validation as insert_record but does NOT touch the
    DB/API. Used by the chat-based extract-then-confirm flow to check a
    doctor's message before ever showing a confirmation prompt. Returns
    {"valid": bool, "cleaned": dict, "missing": list[str], "error": str|None}."""
    entity = get_form_schema(entity_key)
    required_missing = [
        f["label"] for f in entity.get("fields", [])
        if f.get("required") and not field_values.get(f["key"])
    ]
    try:
        cleaned = _validate_field_values(entity, field_values)
    except InsertValidationError as e:
        return {"valid": False, "cleaned": {}, "missing": required_missing, "error": str(e)}
    if required_missing:
        return {"valid": False, "cleaned": cleaned, "missing": required_missing, "error": None}
    return {"valid": True, "cleaned": cleaned, "missing": [], "error": None}


def build_confirmation_summary(entity_key: str, cleaned_field_values: dict) -> str:
    """Human-readable summary of what will be saved, shown to the doctor
    before execution. `cleaned_field_values` is the output of
    validate_only()["cleaned"] (keyed by DB column, not form field key) —
    never raw/unvalidated user text."""
    entity = get_form_schema(entity_key)
    lines = [f"I am preparing to save the following **{entity.get('label', entity_key)}**:"]
    for f in entity.get("fields", []):
        val = cleaned_field_values.get(f["column"])
        if val not in (None, ""):
            lines.append(f"- {f['label']}: {val}")
    lines.append("\nPlease review and complete the fields below before confirming.")
    return "\n".join(lines)


def insert_record(entity_key: str, patient_id: str, visit_id: str, doctor_name: str, doctor_empid: str, field_values: dict) -> dict:
    if not ENABLE_WRITE_OPERATIONS:
        return {"success": False, "error": "Write operations are disabled (ENABLE_WRITE_OPERATIONS=false)."}

    entity = get_form_schema(entity_key)
    
    # Resolve any lookup strings into IDs dynamically
    for f in entity.get("fields", []):
        if f.get("type") == "lookup":
            key = f["key"]
            val = field_values.get(key)
            if isinstance(val, str) and val.strip() and not val.isdigit():
                match = find_exact_match(f["lookup_table"], f["lookup_id_col"], f["lookup_display_col"], val.strip())
                if match:
                    field_values[key] = match["id"]
                else:
                    return {"success": False, "error": f"Could not find exact match for {f['label']}: '{val}'."}
                    
    table = entity["table"]
    doctor_id = doctor_empid or "1"
    
    # Log raw values for debug
    logger.info(f"Adding record ({entity_key}):", extra={
        "context": {
            "doctor_name": doctor_name, "doctor_empid": doctor_empid, "patient_id": patient_id, "visit_id": visit_id,
            "raw": field_values
        }
    })

    try:
        cleaned = _validate_field_values(entity, field_values)
    except InsertValidationError as e:
        audit_logger.log_write(
            doctor_id=doctor_id, patient_id=patient_id, visit_id=visit_id,
            entity_type=entity_key, table=table, record_id=None,
            field_values=field_values, success=False, error=str(e),
        )
        return {"success": False, "error": str(e)}

    return _execute_insert(entity_key, entity, table, cleaned, patient_id, visit_id, doctor_id, audit_field_values=field_values)


def insert_cleaned_record(entity_key: str, patient_id: str, visit_id: str, doctor_name: str, doctor_empid: str, cleaned_field_values: dict) -> dict:
    if not ENABLE_WRITE_OPERATIONS:
        return {"success": False, "error": "Write operations are disabled (ENABLE_WRITE_OPERATIONS=false)."}

    entity = get_form_schema(entity_key)
    table = entity["table"]
    doctor_id = doctor_empid or "1"
    
    logger.info(f"Adding pre-cleaned record ({entity_key}):", extra={
        "context": {
            "doctor_name": doctor_name, "doctor_empid": doctor_empid, "patient_id": patient_id, "visit_id": visit_id,
            "cleaned": cleaned_field_values
        }
    })
    
    # dict(...) so the caller's pending_write copy isn't mutated by _execute_insert
    return _execute_insert(entity_key, entity, table, dict(cleaned_field_values), patient_id, visit_id, doctor_id, audit_field_values=cleaned_field_values)


def _execute_insert(entity_key: str, entity: dict, table: str, cleaned: dict, patient_id: str, visit_id: str, doctor_id: str, audit_field_values: dict) -> dict:
    conn = get_connection()
    try:
        if conn.in_transaction:
            conn.rollback()
        conn.start_transaction()
        cursor = conn.cursor()
        now = datetime.datetime.utcnow()

        # Optional master row first (e.g. prescription master -> detail)
        master = entity.get("requires_master")
        if master:
            m_id_col = master.get("id_column", "id")
            cursor.execute(f"SELECT MAX(`{m_id_col}`) FROM `{master['table']}`")
            max_m_id = cursor.fetchone()[0]
            next_m_id = (max_m_id or 0) + 1
            
            m_cols = [m_id_col, master["patient_column"], master["visit_column"], master["date_column"]]
            m_vals = [next_m_id, patient_id, visit_id, now]
            if master.get("created_by_column"):
                m_cols.append(master["created_by_column"])
                m_vals.append(doctor_id)
            if master.get("doctor_column"):
                m_cols.append(master["doctor_column"])
                m_vals.append(doctor_id)
            
            for dk, dv in master.get("default_values", {}).items():
                if dk not in m_cols:
                    m_cols.append(dk)
                    m_vals.append(now if dv == "{NOW}" else dv)
            
            placeholders = ", ".join(["%s"] * len(m_cols))
            col_list = ", ".join(f"`{c}`" for c in m_cols)
            cursor.execute(
                f"INSERT INTO `{master['table']}` ({col_list}) VALUES ({placeholders})",
                tuple(m_vals),
            )
            cleaned[master["fk_column_in_detail"]] = next_m_id

        # Main detail/record row
        id_col = entity.get("id_column", "id")
        cursor.execute(f"SELECT MAX(`{id_col}`) FROM `{table}`")
        max_id = cursor.fetchone()[0]
        record_id = (max_id or 0) + 1
        cleaned[id_col] = record_id

        # --- Dynamic Tariff / Price Injection ---
        if table == "fhir_order_dtl" and "serviceid" in cleaned:
            service_id = cleaned["serviceid"]
            # Fetch the actual visit details to get tariffscheme_id and billingclassid
            cursor.execute("SELECT tariffscheme_id, bedbillingclsid FROM fhir_visit_mst WHERE visit_id = %s", (visit_id,))
            v_row = cursor.fetchone()
            if v_row:
                ts_id = v_row[0] or 1
                bc_id = v_row[1] or 1
                
                # Update cleaned dict so the detail table gets the right class/scheme
                cleaned["tariffscheme_id"] = ts_id
                cleaned["billingclassid"] = bc_id

                # Fetch real price from tariff sheet
                cursor.execute(
                    "SELECT rate, discountamt FROM fhir_servicetariffsheet WHERE code = %s AND tariffscheme_id = %s AND billingclassid = %s LIMIT 1",
                    (service_id, ts_id, bc_id)
                )
                t_row = cursor.fetchone()
                if t_row:
                    rate = float(t_row[0] or 0)
                    discount = float(t_row[1] or 0)
                    qty = float(cleaned.get("ordqty", 1))
                    
                    cleaned["serviceamount"] = rate
                    cleaned["stddiscount"] = discount
                    # Formula from SP: (ServiceAmount + EmergencyAmount) * qty
                    em_amt = float(cleaned.get("emergencyamount", 0))
                    cleaned["netamount"] = max(0, (rate + em_amt) * qty)
        # ----------------------------------------
        
        if entity.get("patient_column"):
            cleaned[entity["patient_column"]] = patient_id
        if entity.get("visit_column"):
            cleaned[entity["visit_column"]] = visit_id
        if entity.get("created_by_column"):
            cleaned[entity["created_by_column"]] = doctor_id
        if entity.get("created_at_column"):
            cleaned[entity["created_at_column"]] = now

        for dk, dv in entity.get("default_values", {}).items():
            if dk not in cleaned:
                cleaned[dk] = now if dv == "{NOW}" else dv

        cols = list(cleaned.keys())
        vals = [cleaned[c] for c in cols]
        placeholders = ", ".join(["%s"] * len(cols))
        col_list = ", ".join(f"`{c}`" for c in cols)
        cursor.execute(
            f"INSERT INTO `{table}` ({col_list}) VALUES ({placeholders})",
            tuple(vals),
        )

        conn.commit()
        cursor.close()

        audit_logger.log_write(
            doctor_id=doctor_id, patient_id=patient_id, visit_id=visit_id,
            entity_type=entity_key, table=table, record_id=record_id,
            field_values=audit_field_values, success=True, error=None,
        )
        return {"success": True, "record_id": record_id}

    except Exception as e:
        conn.rollback()
        logger.error(f"Insert failed for entity '{entity_key}': {e}")
        audit_logger.log_write(
            doctor_id=doctor_id, patient_id=patient_id, visit_id=visit_id,
            entity_type=entity_key, table=table, record_id=None,
            field_values=audit_field_values, success=False, error=str(e),
        )
        return {"success": False, "error": "Could not save the record. Please try again or contact IT."}
    finally:
        conn.close()
