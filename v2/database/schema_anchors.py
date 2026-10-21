"""Dynamically identify the master "anchor" tables from the live schema.

Used to keep prompt text and planner heuristics free of hardcoded table names:
the patient / visit / bill / order masters are derived from the foreign-key
structure and column shapes of the schema, not from literal table-name literals.
"""

import json
import os

_EXTRA_RELATIONSHIPS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extra_relationships.json")

from config.logging import get_logger

logger = get_logger(__name__)

# Common naming conventions across different hospital DB schemas.
# Override via .env if your DB uses something else entirely.
PATIENT_FK_CANDIDATES = os.getenv("PATIENT_FK_CANDIDATES", "patientid,patient_id,pat_id").split(",")
PATIENT_PK_CANDIDATES = os.getenv("PATIENT_PK_CANDIDATES", "id,patient_id,pid").split(",")

MAPPINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "table_mappings.json")
CRITICAL_ANCHORS = {"patient", "visit"}

def load_table_mappings(schema: dict) -> dict:
    """Load the frozen table mappings and verify they still exist in the live schema."""
    if not os.path.exists(MAPPINGS_FILE):
        raise RuntimeError(
            f"{MAPPINGS_FILE} not found. Run 'python discover_schema_anchors.py' first."
        )
        
    with open(MAPPINGS_FILE, "r", encoding="utf-8") as f:
        anchors = json.load(f)
        
    # Staleness Check
    for key, val in anchors.items():
        table_name = val.get("table") if isinstance(val, dict) else val
        if not table_name or table_name not in schema:
            if key in CRITICAL_ANCHORS:
                raise RuntimeError(f"[SCHEMA MISMATCH] Critical anchor '{key}' -> '{table_name}' not found in live DB. Re-run discover_schema_anchors.py")
            else:
                logger.error(f"[SCHEMA MISMATCH] Optional anchor '{key}' -> '{table_name}' not found. Feature will degrade gracefully.")
                
    return anchors



def merge_extra_relationships(schema: dict) -> dict:
    """Enrich a schema with relationships the DB does not declare as FKs.

    Reads `extra_relationships.json` (a list of {table, column_name,
    referenced_table, referenced_column}) and appends them to each table's
    `foreign_keys` so the relationship graph can discover join paths (e.g. the
    prescription -> drug_sale -> patient chain). Returns the same dict, mutated.
    """
    if not os.path.exists(_EXTRA_RELATIONSHIPS_FILE):
        return schema
    with open(_EXTRA_RELATIONSHIPS_FILE, encoding="utf-8") as f:
        extra = json.load(f)
    for rel in extra:
        table = rel.get("table")
        if table not in schema:
            continue
        fk = {
            "column_name": rel.get("column_name"),
            "referenced_table": rel.get("referenced_table"),
            "referenced_column": rel.get("referenced_column"),
        }
        existing = schema[table].get("foreign_keys", [])
        if all(fk["column_name"] != e.get("column_name") or fk["referenced_table"] != e.get("referenced_table")
               for e in existing):
            schema[table].setdefault("foreign_keys", []).append(fk)
    return schema


def find_anchor_tables(schema: dict) -> dict:
    """Return {'patient', 'visit', 'bill', 'order'} master table names, if findable."""
    anchors: dict = {}

    # Tables referenced by a `patientid` FK are transactional; their target is the patient master.
    patient_refs: dict = {}
    # Tables referenced by a `bill_id` / `order_id` FK are their masters' details.
    bill_refs: dict = {}
    order_refs: dict = {}

    for table, info in schema.items():
        cols = {c["column_name"] for c in info.get("columns", [])}
        for fk in info.get("foreign_keys", []):
            src, ref_tbl, ref_col = fk["column_name"], fk["referenced_table"], fk["referenced_column"]
            if src in PATIENT_FK_CANDIDATES and ref_col in PATIENT_PK_CANDIDATES:
                patient_refs.setdefault(ref_tbl, []).append(table)
            elif src == "bill_id":
                bill_refs.setdefault(ref_tbl, []).append(table)
            elif src in ("order_id", "ordid"):
                order_refs.setdefault(ref_tbl, []).append(table)

    def most_referenced(refs: dict) -> str | None:
        return max(refs, key=lambda t: len(refs[t])) if refs else None

    patient = most_referenced(patient_refs)
    if patient:
        anchors["patient"] = patient

    bill = most_referenced(bill_refs)
    if bill:
        anchors["bill"] = bill

    order = most_referenced(order_refs)
    if order:
        anchors["order"] = order

    # Visit master: a table with a patient link and its own id, named like a visit.
    # (Excludes the patient master itself.)
    for table, info in schema.items():
        cols = {c["column_name"].lower() for c in info.get("columns", [])}
        if table == patient:
            continue
        if any(c in cols for c in PATIENT_PK_CANDIDATES) and any(c in cols for c in PATIENT_FK_CANDIDATES) and "visit" in table.lower():
            anchors["visit"] = table
    return anchors

def get_fk_join(from_table: str, to_table: str, schema: dict, via_column: str = None) -> dict:
    """Finds the foreign key relationship between two tables in the schema.
    
    Returns a dict with 'column_name', 'referenced_table', and 'referenced_column'.
    If multiple paths exist and via_column is not provided, raises ValueError.
    If no path is found, raises ValueError.
    """
    if from_table not in schema:
        raise ValueError(f"Table '{from_table}' not found in schema cache.")
        
    fks = schema[from_table].get("foreign_keys", [])
    
    matches = [fk for fk in fks if fk["referenced_table"] == to_table]
    
    if not matches:
        # Check reverse direction
        if to_table in schema:
            reverse_fks = schema[to_table].get("foreign_keys", [])
            reverse_matches = [fk for fk in reverse_fks if fk["referenced_table"] == from_table]
            if reverse_matches:
                # Return inverted perspective
                return {
                    "column_name": reverse_matches[0]["referenced_column"],
                    "referenced_table": to_table,
                    "referenced_column": reverse_matches[0]["column_name"]
                }
                
        raise ValueError(f"No foreign key found from '{from_table}' to '{to_table}'.")
        
    if via_column:
        for m in matches:
            if m["column_name"].lower() == via_column.lower():
                return m
        raise ValueError(f"Foreign key to '{to_table}' via '{via_column}' not found on '{from_table}'.")
        
    if len(matches) > 1:
        paths = [m["column_name"] for m in matches]
        raise ValueError(
            f"Ambiguous foreign key path from '{from_table}' to '{to_table}'. "
            f"Multiple columns point to the target: {paths}. "
            f"You must specify via_column to disambiguate."
        )
        
    return matches[0]
