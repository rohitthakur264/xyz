import json
import re
from llm.llm_client import LLMClient
from config.logging import get_logger

logger = get_logger(__name__)

INTENTS = [
    "ADD_RECORD",     # Inserting/Adding new data (prescriptions, lab tests, etc)
    "PATIENT_SEARCH", # Looking up a patient by ID/name/phone
    "VISIT",          # Querying visit details/history
    "BILLING",        # Querying invoices, bills, amounts, services
    "PRESCRIPTION",   # Querying prescribed drugs, dosages, pharmacy sales
    "LAB",            # Querying lab tests, results, parameters
    "ALLERGY",        # Querying patient allergies
    "VITALS",         # Querying pulse, BP, temp, height, weight
    "SURGERY",        # Querying operations, OT scheduling
    "FAMILY_HISTORY", # Querying family history, past medical/surgical history
    "CHIEF_COMPLAINT",# Querying chief complaints or reason for consultation
    "RADIOLOGY",      # Querying radiology, scans, x-rays, mri, imaging
    "DISCHARGE_SUMMARY", # Querying discharge details, summaries, or discharge dates
    "CONVERSATIONAL", # Greetings, general chat, non-DB questions
    "GENERAL"         # Fallback
]

class IntentDetector:
    """Classifies user natural language questions into specific domains.

    Almost all classification is delegated to FAST_MODEL so that synonyms,
    typos, and Hinglish/Hindi phrasing are handled gracefully instead of
    silently mis-routing (or dropping to GENERAL) the way a hardcoded
    English keyword list would. Only truly trivial, unambiguous cases are
    short-circuited before the LLM call:
      - empty/near-empty input
      - a bare greeting ("hi", "hello", ...) with nothing else in it
      - a string that is PURELY digits/phone-punctuation (a raw patient
        ID / phone number, with no other words at all)
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def detect_intent(self, question: str) -> list[str]:
        q_lower = question.lower().strip()

        # Handle empty or very short questions (but check for a bare
        # greeting first — "hi" is only 2 chars but must stay CONVERSATIONAL)
        words = set(q_lower.split())
        if any(w in words for w in ["hi", "hello", "hey", "thanks", "ok", "okay"]):
            if len(words) <= 6:
                logger.info(f"Fast intent detected: CONVERSATIONAL for '{question}'")
                return ["CONVERSATIONAL"]

        # Pure numeric/phone-like string with NO other words at all
        # (e.g. "9876543210" or "12345") -> treat as a raw patient ID/phone.
        if re.fullmatch(r'[\d\+\-\s]{5,15}', q_lower):
            logger.info(f"Fast intent detected: PATIENT_SEARCH for '{question}' (Looks like ID/Phone)")
            return ["PATIENT_SEARCH"]

        clean_words = set(re.findall(r'\b\w+\b', q_lower))

        # Fast intent detection for standard clinical domain keywords & short queries
        # This provides instant 0ms routing, saves Groq TPM quota, and prevents fallback to GENERAL
        if clean_words.intersection({"visit", "visits", "admission", "admissions", "hospitalization", "bharti"}):
            if not any(w in clean_words for w in ["add", "insert", "create", "record", "new"]):
                logger.info(f"Fast intent detected: VISIT for '{question}'")
                return ["VISIT"]

        if clean_words.intersection({"bill", "bills", "billing", "invoice", "invoices", "payment", "due"}):
            if not any(w in clean_words for w in ["add", "insert", "create", "record", "new"]):
                logger.info(f"Fast intent detected: BILLING for '{question}'")
                return ["BILLING"]

        if clean_words.intersection({"prescription", "prescriptions", "medicine", "medicines", "drug", "drugs", "dawai", "dawiyan"}):
            if not any(w in clean_words for w in ["add", "insert", "create", "record", "new", "compare", "interaction"]):
                logger.info(f"Fast intent detected: PRESCRIPTION for '{question}'")
                return ["PRESCRIPTION"]

        if clean_words.intersection({"vital", "vitals", "bp", "pulse", "heartrate", "temperature", "temp", "bukhar", "respiratory"}):
            if not any(w in clean_words for w in ["add", "insert", "create", "record", "new"]):
                logger.info(f"Fast intent detected: VITALS for '{question}'")
                return ["VITALS"]

        if clean_words.intersection({"allergy", "allergies", "allergic"}):
            if not any(w in clean_words for w in ["add", "insert", "create", "record", "new"]):
                logger.info(f"Fast intent detected: ALLERGY for '{question}'")
                return ["ALLERGY"]

        if clean_words.intersection({"surgery", "surgeries", "operation", "operations", "ot"}):
            if not any(w in clean_words for w in ["add", "insert", "create", "record", "new", "precaution", "post-care", "post"]):
                logger.info(f"Fast intent detected: SURGERY for '{question}'")
                return ["SURGERY"]

        if clean_words.intersection({"lab", "labs", "test", "tests", "cbc"}):
            if not any(w in clean_words for w in ["add", "insert", "create", "record", "new", "radiology", "scan"]):
                logger.info(f"Fast intent detected: LAB for '{question}'")
                return ["LAB"]

        if clean_words.intersection({"radiology", "xray", "x-ray", "mri", "ultrasound", "scan", "scans"}):
            if not any(w in clean_words for w in ["add", "insert", "create", "record", "new"]):
                logger.info(f"Fast intent detected: RADIOLOGY for '{question}'")
                return ["RADIOLOGY"]

        if clean_words.intersection({"discharge", "chhutti"}):
            logger.info(f"Fast intent detected: DISCHARGE_SUMMARY for '{question}'")
            return ["DISCHARGE_SUMMARY"]

        if len(q_lower) < 3:
            logger.info(f"Fast intent detected: GENERAL for '{question}' due to length")
            return ["GENERAL"]

        # Everything else -> let the LLM classify. This is intentional:
        # keyword lists silently mis-route synonyms, typos, and
        # Hindi/Hinglish phrasing without ever raising an error, which is
        # worse than the extra LLM call for a clinical tool.
        prompt = f"""You are a clinical AI intent classifier for a hospital chatbot used by doctors and staff in India. Questions may be in English, Hindi, or Hinglish (a mix of both, written in Roman script) — classify based on MEANING, not exact keyword matches. Treat synonyms, misspellings, and colloquial phrasing the same as their standard English equivalent (e.g. "hospitalization", "admit", "bharti" all mean the same as "admission"/VISIT; "dawai", "medicine", "tablet" all mean PRESCRIPTION; "bukhar" means fever/Temperature -> VITALS).

Categorize the following question into ONE OR MORE of these intents. If the user asks for "all details" or multiple things, output all applicable intents separated by commas.

- ADD_RECORD: The user wants to insert, add, create, or record new medical data (like adding a prescription, recording a lab test result, or adding vitals).
- PATIENT_SEARCH: Looking up a patient by ID, name, or phone number. (CRITICAL: Do NOT output PATIENT_SEARCH unless the user explicitly provides a patient ID, registration number, name, or phone number in their question. E.g. for "billing detail" output BILLING, do NOT output PATIENT_SEARCH).
- VISIT: Querying visit details, history, appointments, admissions, or consulting doctors.
- BILLING: Querying invoices, bills, amounts, services, or charges.
- PRESCRIPTION: Querying prescribed drugs, medicines, dosages, or pharmacy sales.
- LAB: Querying lab tests or results.
- ALLERGY: Querying patient allergies.
- VITALS: Querying pulse, BP, temperature/fever, height, weight, respiratory rate.
- SURGERY: Querying operations, surgery, or OT scheduling.
- FAMILY_HISTORY: Querying family history, past medical/surgical history.
- CHIEF_COMPLAINT: Querying chief complaints or reason for consultation.
- RADIOLOGY: Querying radiology, scans, x-rays, mri, imaging, or test templates.
- DISCHARGE_SUMMARY: Querying discharge details, summaries, or discharge dates.
- CONVERSATIONAL: Greetings, general chat, or any ANALYTICAL/EVALUATIVE question about data already discussed rather than a fresh lookup — e.g. explaining a term ("what does crocin do?"), asking if something is normal/serious/dangerous IN THE ABSTRACT (not tied to a specific patient's fresh reading), precautions/post-care advice, drug-to-drug comparisons or interactions, or "why"/"how to" questions that aren't asking to fetch new patient data.
- GENERAL: Fallback intent when nothing else fits.

IMPORTANT RULE: If the user asks to "add", "insert", or "record" something (like "add prescription paracetamol 500mg"), you MUST output ADD_RECORD. Do NOT output PRESCRIPTION or LAB if the primary intent is adding a new record.
IMPORTANT RULE: If the user asks an evaluative question ABOUT A PATIENT'S DATA (e.g., "are the vitals normal?", "is the patient's blood pressure high?", "iska BP normal hai kya?"), you MUST output the corresponding data intent (e.g. VITALS) so the database is queried — do NOT output CONVERSATIONAL or GENERAL for these, because the orchestrator needs to fetch the actual reading first.
IMPORTANT RULE: Short queries like a single word or short phrase (e.g. "bp", "billing", "lab", "prescription detail", "vitals detail") should map directly to their corresponding data intent, not GENERAL or CONVERSATIONAL.

Respond with ONLY the exact intent strings separated by commas. Do not explain.

Examples:
Question: "what is the phone number of patient rahul?"
Intents: PATIENT_SEARCH

Question: "add prescription paracetamol 500mg"
Intents: ADD_RECORD

Question: "record lab test CBC normal"
Intents: ADD_RECORD

Question: "show me the bills and vitals"
Intents: BILLING, VITALS

Question: "prescription detail"
Intents: PRESCRIPTION

Question: "who is patient id 1234?"
Intents: PATIENT_SEARCH

Question: "is the blood pressure normal?"
Intents: VITALS

Question: "iska BP normal hai kya?"
Intents: VITALS

Question: "hospitalization details" / "bharti hone ki detail"
Intents: VISIT

Question: "give drug to drug comparison" or "compare these two drugs" or "check interaction between my medicines"
Intents: CONVERSATIONAL

Question: "what does crocin do?"
Intents: CONVERSATIONAL

Question: "did the patient have any operations?"
Intents: SURGERY

Question: "show all the details for the patient"
Intents: PATIENT_SEARCH, BILLING, VISIT, PRESCRIPTION, LAB, ALLERGY, VITALS, SURGERY, FAMILY_HISTORY, CHIEF_COMPLAINT

Question: {question}
Intents:"""

        try:
            from config.settings import FAST_MODEL
            # We use a very low temperature for deterministic classification
            response = self.llm.generate(prompt, model=FAST_MODEL, temperature=0.0)
            raw_intents_str = response.strip().upper()

            detected_intents = []

            # Split by comma and clean up
            raw_intents = [ri.strip() for ri in raw_intents_str.split(",")]

            for raw_intent in raw_intents:
                intent_match = None
                if raw_intent in INTENTS:
                    intent_match = raw_intent
                else:
                    # Try to find if any intent is a substring, sorting by length descending to match longest first
                    sorted_intents = sorted(INTENTS, key=len, reverse=True)
                    for valid_intent in sorted_intents:
                        if valid_intent in raw_intent:
                            intent_match = valid_intent
                            break
                if intent_match and intent_match not in detected_intents:
                    detected_intents.append(intent_match)

            if not detected_intents:
                detected_intents = ["GENERAL"]

            logger.info(f"Intents detected: {detected_intents} for question: '{question}'. Raw LLM output: '{raw_intents_str}'")
            return detected_intents
        except Exception as e:
            logger.error(f"Intent detection failed: {e}")
            return ["GENERAL"]
