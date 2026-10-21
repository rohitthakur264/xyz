"""
Natural-language -> structured fields extractor for the chat-based
"add record" flow (prescription / lab test / vitals / ...).

CRITICAL SAFETY NOTE: this module's only job is to turn free text into a
JSON dict of {field_key: value} for a KNOWN entity from insert_schema.json.
It never touches the database and never decides to execute anything.
Its output is untrusted input, exactly like anything else the LLM produces
- services/insert_service.py's _validate_field_values() (the same
allow-list/type/range validator used by the old form path) is ALWAYS run
on the result before it's shown to the doctor for confirmation, and
nothing is written until the doctor explicitly confirms.
"""

import json
from services import insert_service
from config.logging import get_logger

logger = get_logger(__name__)


def _build_prompt(text: str) -> str:
    entities = insert_service.INSERT_SCHEMA.get("entities", {})
    entity_descriptions = []
    for key, entity in entities.items():
        field_lines = []
        for f in entity.get("fields", []):
            req = "required" if f.get("required") else "optional"
            extra = ""
            if f.get("type") == "number":
                extra = f" (number{', min ' + str(f['min']) if 'min' in f else ''}{', max ' + str(f['max']) if 'max' in f else ''})"
            elif f.get("type") == "lookup":
                extra = " (name of a value to look up - e.g. a drug name)"
            elif f.get("type") == "datetime":
                extra = " (date/time - if not mentioned, use null and it will default to now)"
            field_lines.append(f'    - "{f["key"]}": {f["label"]}{extra} [{req}]')
        entity_descriptions.append(f'  "{key}":\n' + "\n".join(field_lines))

    schema_text = "\n".join(entity_descriptions)

    return f"""You extract structured data from a doctor's message for a hospital record-entry system. You do NOT decide anything and you do NOT execute anything - you only extract.

Available entity types and their fields:
{schema_text}

Rules:
- Pick the ONE entity type that best matches the message. If the message doesn't look like a request to add/record/log a {'/'.join(entities.keys())}, set "entity_type" to null.
- Only extract fields that are explicitly stated or clearly implied in the message. Do NOT invent, guess, or default a value that wasn't given (leave it null instead) - except datetime fields, which may default to null (meaning "now").
- For a "lookup" type field, extract the plain-text name the user said (e.g. "paracetamol") - do not invent an ID.
- Respond with ONLY valid JSON, no explanation, in exactly this shape:
{{"entity_type": "<one of the keys above, or null>", "field_values": {{"<field_key>": <value or null>, ...}}}}

Examples:
Message: "add prescription: paracetamol 500mg, twice a day, for 5 days"
Response: {{"entity_type": "prescription", "field_values": {{"drug_id": "paracetamol", "dosage": "500mg", "frequency_id": "twice a day", "duration_days": 5, "instructions": null}}}}

Message: "record vitals: bp 118/76, temp 37.2, pulse 68, rr 18"
Response: {{"entity_type": "vitals", "field_values": {{"systolic_bp": 118, "diastolic_bp": 76, "temperature": 37.2, "pulse": 68, "respiratory_rate": 18, "recorded_at": null}}}}

Message: "add lab test cbc 10.5 g/dL, normal 12-16"
Response: {{"entity_type": "lab_test", "field_values": {{"test_name": "CBC", "result": "10.5", "paramunit": "g/dL", "paramnormalrange": "12-16", "test_date": null, "remarks": null}}}}

Message: "add hemoglobin 11.2, patient thoda anemic lag raha hai"
Response: {{"entity_type": "lab_test", "field_values": {{"test_name": "hemoglobin", "result": "11.2", "paramunit": null, "paramnormalrange": null, "test_date": null, "remarks": "patient thoda anemic lag raha hai"}}}}

Message: "what is the patient's BP?"
Response: {{"entity_type": null, "field_values": {{}}}}

Message: "{text}"
Response:"""


def extract(text: str, llm_client, model: str) -> dict:
    """Returns {"entity_type": str|None, "field_values": dict}. Never
    raises for a malformed LLM response - falls back to entity_type=None
    so the caller treats it as "couldn't understand", not as "safe to
    execute with partial data"."""
    prompt = _build_prompt(text)
    try:
        raw = llm_client.generate(prompt, model=model, temperature=0.0)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)
        entity_type = parsed.get("entity_type")
        field_values = parsed.get("field_values", {}) or {}
        if entity_type not in insert_service.INSERT_SCHEMA.get("entities", {}):
            entity_type = None
            field_values = {}
        return {"entity_type": entity_type, "field_values": field_values}
    except Exception as e:
        logger.warning(f"record_extractor: could not parse LLM output ({e}); treating as no-match.")
        return {"entity_type": None, "field_values": {}}
