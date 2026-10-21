from typing import Optional, List, Dict
import re
from memory.visit_context import VisitContext
from services.document_generator import DocumentGenerator
from config.logging import get_logger

logger = get_logger(__name__)

class VisitResolver:
    """Resolves and disambiguates the active visit from user input."""
    
    def __init__(self):
        self.doc_gen = DocumentGenerator()

    def fetch_patient_visits(self, patient_id: int) -> List[Dict]:
        """Fetch all visits for a patient."""
        return self.doc_gen.fetch_visit_info(patient_id)

    def resolve_from_question(self, question: str, patient_id: int) -> tuple[Optional[VisitContext], Optional[str]]:
        """
        Attempts to resolve a visit from the question.
        Returns:
            (VisitContext, None) if resolved successfully.
            (None, disambiguation_message) if ambiguous or none found.
        """
        visits = self.fetch_patient_visits(patient_id)
        
        if not visits:
            return None, "No visits found for this patient."

        # If only one visit exists, auto-select it
        if len(visits) == 1:
            visit = visits[0]
            logger.info(f"Auto-selected single visit {visit['Visit ID']}")
            return VisitContext(
                visit_id=visit['Visit ID'],
                patient_id=str(patient_id),
                visit_type=visit['Visit Type'],
                department=visit['Department']
            ), None

        # Check if user asked for the latest visit
        q_lower = question.lower()
        if any(kw in q_lower for kw in ["latest visit", "last visit", "current visit", "latest one", "last one"]):
            visit = visits[0]
            logger.info(f"Resolved latest visit {visit['Visit ID']} from question text")
            return VisitContext(
                visit_id=visit['Visit ID'],
                patient_id=str(patient_id),
                visit_type=visit['Visit Type'],
                department=visit['Department'],
                visit_no=str(visit.get('Visit No', visit.get('Visit No.', ''))),
                visit_date=str(visit.get('Visit Date/Time', ''))
            ), None

        # Check if the user specified a known visit number in the query
        for v in visits:
            v_no = str(v.get("Visit No", "")).strip().lower()
            if not v_no:
                v_no = str(v.get("Visit No.", "")).strip().lower()
            if v_no and v_no in q_lower:
                logger.info(f"Resolved visit {v['Visit ID']} from question text")
                return VisitContext(
                    visit_id=v['Visit ID'],
                    patient_id=str(patient_id),
                    visit_type=v['Visit Type'],
                    department=v['Department'],
                    visit_no=str(v.get('Visit No', v.get('Visit No.', ''))),
                    visit_date=str(v.get('Visit Date/Time', ''))
                ), None

        # If > 1 visit and none explicitly matched, ask to disambiguate
        options = []
        for i, v in enumerate(visits, 1):
            options.append(f"{i}. **{v['Visit No']}** on {v['Visit Date/Time']} (Dept: {v['Department']})")
            
        msg = "This patient has multiple visits. Please specify which visit you want to use by mentioning its Visit No:\n" + "\n".join(options)
        return None, msg
