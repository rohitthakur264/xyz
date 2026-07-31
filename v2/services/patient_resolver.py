import re
from typing import Optional
from memory.patient_context import PatientContext
from database.query_executor import QueryExecutor
from config.logging import get_logger

logger = get_logger(__name__)

class PatientResolver:
    """Service to extract patient identifiers from natural language and resolve them against the database."""
    
    def __init__(self, query_executor: Optional[QueryExecutor] = None):
        self.executor = query_executor or QueryExecutor()

    def extract_identifier(self, question: str) -> Optional[dict]:
        """
        Regex and rule-based extraction of patient ID/registration number/name from prompt.
        Returns dict with keys: {'value': str, 'type': 'id'|'registration_no'|'name'|'unknown'} or None.
        """
        patterns = [
            (r"\b(?:patient|reg|registration|pat)\s*(?:no|num|number|id|#)\s*[:=]?\s*([A-Za-z0-9_-]+)\b", "registration_no"),
            (r"\b(?:id|ID)\s*[:=]?\s*(\d+)\b", "id"),
            (r"\bfor\s+patient\s+([A-Za-z0-9_\s-]+)\b", "name"),
            (r"\b(\d{5,8})\b", "id"),
        ]
        
        ignored_words = {
            "the", "a", "an", "details", "info", "data", "records", "history", 
            "billing", "s", "is", "was", "has", "had", "name", "profile", 
            "list", "report", "summary", "visit", "prescription", "lab", "test"
        }
        
        for pattern, id_type in patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                val = match.group(1).strip().lstrip("'").strip()
                if val.lower() not in ignored_words:
                    return {"value": val, "type": id_type}
                    
        return None

    def resolve_patient(self, identifier: str, identifier_type: str = "unknown") -> Optional[PatientContext]:
        """Queries fhir_patient_mst to resolve the given identifier into a PatientContext."""
        if not identifier:
            return None
            
        logger.info(f"Attempting to resolve patient identifier: '{identifier}' (type: {identifier_type})")
        
        try:
            if identifier_type == "registration_no":
                sql = f"SELECT id, registration_no, display FROM fhir_patient_mst WHERE registration_no = '{identifier}'"
            elif identifier_type == "id" and identifier.isdigit():
                sql = f"SELECT id, registration_no, display FROM fhir_patient_mst WHERE id = {int(identifier)}"
            else:
                sql = f"SELECT id, registration_no, display FROM fhir_patient_mst WHERE registration_no = '{identifier}'"
                
            res = self.executor.execute(sql)
            if not (res.get("success") and res.get("rows")) and identifier.isdigit():
                # Fallback to checking id column
                id_sql = f"SELECT id, registration_no, display FROM fhir_patient_mst WHERE id = {int(identifier)}"
                res = self.executor.execute(id_sql)

            if res.get("success") and res.get("rows"):
                row = res["rows"][0]
                patient_context = PatientContext(
                    patient_id=str(row["id"]),
                    registration_no=str(row.get("registration_no", "")),
                    name=str(row.get("display", ""))
                )
                logger.info(f"Successfully resolved patient context: ID={patient_context.patient_id}, RegNo={patient_context.registration_no}, Name={patient_context.name}")
                return patient_context
                
            # Try fuzzy name matching if not exact match
            name_sql = f"SELECT id, registration_no, display FROM fhir_patient_mst WHERE display LIKE '%{identifier}%'"
            res_name = self.executor.execute(name_sql)
            if res_name.get("success") and res_name.get("rows"):
                row = res_name["rows"][0]
                patient_context = PatientContext(
                    patient_id=str(row["id"]),
                    registration_no=str(row.get("registration_no", "")),
                    name=str(row.get("display", ""))
                )
                logger.info(f"Successfully resolved patient by name: ID={patient_context.patient_id}, Name={patient_context.name}")
                return patient_context
        except Exception as e:
            logger.warning(f"Database query failed during patient resolution ({e}). Using raw identifier as patient context.")
            if identifier.isdigit() or len(identifier) >= 3:
                return PatientContext(patient_id=identifier, registration_no=identifier, name=identifier)
            
        logger.warning(f"Could not resolve patient for identifier '{identifier}'")
        return None

    def resolve_from_question(self, question: str) -> Optional[PatientContext]:
        """Extracts identifier from question and resolves it against the database."""
        extracted = self.extract_identifier(question)
        if extracted:
            return self.resolve_patient(extracted["value"], extracted["type"])
        return None
