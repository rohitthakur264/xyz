import json
from llm.ollama_client import OllamaClient
from config.logging import get_logger

logger = get_logger(__name__)

INTENTS = [
    "PATIENT_SEARCH", # Looking up a patient by ID/name/phone
    "VISIT",          # Querying visit details/history
    "BILLING",        # Querying invoices, bills, amounts, services
    "PRESCRIPTION",   # Querying prescribed drugs, dosages, pharmacy sales
    "LAB",            # Querying lab tests, results, parameters
    "ALLERGY",        # Querying patient allergies
    "VITALS",         # Querying pulse, BP, temp, height, weight
    "SURGERY",        # Querying operations, OT scheduling
    "GENERAL"         # Fallback
]

class IntentDetector:
    """Classifies user natural language questions into specific domains."""
    
    def __init__(self, llm_client: OllamaClient):
        self.llm = llm_client

    def detect_intent(self, question: str) -> str:
        q_lower = question.lower()
        if any(w in q_lower for w in ["visit", "encounter", "admission"]):
            logger.info(f"Fast intent detected: VISIT for '{question}'")
            return "VISIT"
        if any(w in q_lower for w in ["bill", "billing", "invoice", "payment", "amount", "charge", "deposit"]):
            logger.info(f"Fast intent detected: BILLING for '{question}'")
            return "BILLING"
        if any(w in q_lower for w in ["prescript", "medicine", "drug", "pharmacy"]):
            logger.info(f"Fast intent detected: PRESCRIPTION for '{question}'")
            return "PRESCRIPTION"
        if any(w in q_lower for w in ["lab", "test", "result"]):
            logger.info(f"Fast intent detected: LAB for '{question}'")
            return "LAB"
        if any(w in q_lower for w in ["vital", "bp", "pulse", "temp", "weight"]):
            logger.info(f"Fast intent detected: VITALS for '{question}'")
            return "VITALS"
        if any(w in q_lower for w in ["allergy", "allergic"]):
            logger.info(f"Fast intent detected: ALLERGY for '{question}'")
            return "ALLERGY"
        if any(w in q_lower for w in ["reg", "registration", "patient", "mrn"]) and len(question.split()) <= 5:
            logger.info(f"Fast intent detected: PATIENT_SEARCH for '{question}'")
            return "PATIENT_SEARCH"

        prompt = f"""You are a clinical AI intent classifier.
Categorize the following question into exactly ONE of the following intents:
{', '.join(INTENTS)}

Respond with ONLY the intent string. Do not explain.

Question: {question}
Intent:"""

        try:
            # We use a very low temperature for deterministic classification
            response = self.llm.generate(prompt, temperature=0.0)
            intent = response.strip().upper()
            
            # Simple fallback handling
            if intent not in INTENTS:
                # Try to find if any intent is a substring
                for valid_intent in INTENTS:
                    if valid_intent in intent:
                        intent = valid_intent
                        break
                else:
                    intent = "GENERAL"
                    
            logger.info(f"Intent detected: {intent} for question: '{question}'")
            return intent
        except Exception as e:
            logger.error(f"Intent detection failed: {e}")
            return "GENERAL"
