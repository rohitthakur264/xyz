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
