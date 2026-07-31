import json
import time
from dataclasses import dataclass, field
from typing import Optional
import ollama
from config.settings import LLM_MODEL
from db.connection import get_db_connection

@dataclass
class PatientContext:
    patient_id: str
    registration_no: str = ""
    name: str = ""
    age: str = ""
    gender: str = ""
    last_accessed: float = field(default_factory=time.time)
    
    def update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.last_accessed = time.time()

def resolve_patient(identifier: str, identifier_type: str = "unknown") -> dict:
    """
    Looks up the patient by ID, registration_no, or name.
    Returns: {"resolved": True, "patient": {"id": 123, "registration_no": "...", "display": "..."}}
    Or if multiple matches/no match: {"resolved": False, "error": "NEEDS_PATIENT: ..."}
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            id_val = None
            if identifier.isdigit():
                id_val = int(identifier)

            # Check if identifier is exactly an ID or Registration No
            if identifier_type == "registration_no":
                query = "SELECT id, registration_no, display, date_of_birth FROM fhir_patient_mst WHERE registration_no = %s"
                cursor.execute(query, (identifier,))
            elif identifier_type == "id" and id_val is not None:
                query = "SELECT id, registration_no, display, date_of_birth FROM fhir_patient_mst WHERE id = %s"
                cursor.execute(query, (id_val,))
            elif identifier_type == "name":
                cursor.execute("SELECT 1 WHERE 1=0") # skip exact match
            else:
                query = "SELECT id, registration_no, display, date_of_birth FROM fhir_patient_mst WHERE registration_no = %s OR id = %s"
                cursor.execute(query, (identifier, id_val))
                
            exact_matches = cursor.fetchall()
            
            if len(exact_matches) == 1:
                row = exact_matches[0]
                return {
                    "resolved": True,
                    "patient": {"id": row[0], "registration_no": row[1], "display": row[2]}
                }
            elif len(exact_matches) > 1:
                # Should be rare for registration_no, but just in case
                options = [f"[reg {r[1]}, DOB {r[3]}]" for r in exact_matches]
                return {
                    "resolved": False,
                    "error": f"NEEDS_PATIENT: Multiple patients match '{identifier}' exactly — did you mean: {' or '.join(options)}?"
                }
                
            # If no exact match, try name lookup
            like_val = f"%{identifier}%"
            name_query = """
                SELECT id, registration_no, display, date_of_birth
                FROM fhir_patient_mst
                WHERE display LIKE %s OR middle_name LIKE %s OR last_name LIKE %s
            """
            cursor.execute(name_query, (like_val, like_val, like_val))
            name_matches = cursor.fetchall()
            
            if len(name_matches) == 1:
                row = name_matches[0]
                return {
                    "resolved": True,
                    "patient": {"id": row[0], "registration_no": row[1], "display": row[2]}
                }
            elif len(name_matches) > 1:
                options = [f"[reg {r[1]}, DOB {r[3]}]" for r in name_matches[:5]] # Show up to 5
                return {
                    "resolved": False,
                    "error": f"NEEDS_PATIENT: Multiple patients match '{identifier}' — did you mean: {', '.join(options)}?"
                }
            else:
                return {
                    "resolved": False,
                    "error": f"NEEDS_PATIENT: No patient found matching '{identifier}'."
                }
    finally:
        conn.close()

def extract_patient_identifier(raw_question: str) -> dict:
    """
    Extracts a patient identifier from the question and attempts to resolve it.
    Returns: {"has_identifier": True, "patient": {...}, "error": None}
    Or {"has_identifier": True, "patient": None, "error": "NEEDS_PATIENT: ..."}
    Or {"has_identifier": False, "patient": None, "error": None}
    """
    system_prompt = (
        "You are a medical natural language processing tool. Your job is strictly to identify "
        "if a user's message contains a specific patient identifier (like a registration number, patient ID, or a patient's full name).\n"
        "Return ONLY a valid JSON object matching this schema:\n"
        '{"has_identifier": true/false, "value": "the extracted identifier as a string, or null if false", "type": "registration_no" | "id" | "name" | "unknown"}\n'
        "CRITICAL RULE: Extract ONLY the pure value in 'value'. Strip away any prefix words like 'registration no', 'patient id', 'reg', or 'id'. "
        "For example, if the user says 'registration no 165881', you must return value='165881' and type='registration_no'.\n"
        "If they say 'id 165881', return type='id'. If they say 'John Doe', return type='name'. If no prefix is given, return type='unknown'.\n"
        "If they say '[reg 165881, DOB...]', extract '165881' as type='registration_no'.\n"
        "Do not include any explanation or markdown formatting."
    )
    
    try:
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Message: {raw_question}"}
            ],
            format='json',
            options={'temperature': 0.0}
        )
        
        content = response['message']['content'].strip()
        data = json.loads(content)
        
        has_id = bool(data.get("has_identifier", False))
        identifier_value = str(data.get("value")) if data.get("value") else None
        identifier_type = str(data.get("type", "unknown"))
        
        if has_id and identifier_value:
            resolved_data = resolve_patient(identifier_value, identifier_type)
            return {
                "has_identifier": True,
                "patient": resolved_data.get("patient"),
                "error": resolved_data.get("error")
            }
            
        return {
            "has_identifier": False,
            "patient": None,
            "error": None
        }
    except Exception as e:
        print(f"Error extracting patient context: {e}")
        return {"has_identifier": False, "patient": None, "error": None}

def get_patient_details(patient_id: int) -> dict:
    """
    Deterministically fetches the patient master profile record for a resolved patient ID.
    Returns {"columns": [...], "rows": [...], "patient": {...}}
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT p.id, p.registration_no, p.display, p.date_of_birth
                FROM fhir_patient_mst p
                WHERE p.id = %s
            """
            cursor.execute(query, (patient_id,))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            str_rows = [[str(val) if val is not None else "" for val in r] for r in rows]
            return {
                "columns": columns,
                "rows": str_rows,
                "sql_used": f"SELECT id, registration_no, display, date_of_birth FROM fhir_patient_mst WHERE id = {patient_id}"
            }
    finally:
        conn.close()
