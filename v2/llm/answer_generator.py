import json
import os
from llm.llm_client import LLMClient
from config.settings import ANSWER_MODEL
from config.logging import get_logger

logger = get_logger(__name__)



class AnswerGenerator:
    """Generates human-readable summaries of database results."""
    
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def generate(self, question: str, sql: str, rows: list, patient_context=None) -> str:
        """
        Takes raw database rows and generates a friendly clinical answer.
        Does NOT hallucinate data. If rows is empty, explicitly says so.
        `patient_context` (optional) maps the patient the doctor asked about to the
        internal ids used in the data rows, so the summarizer does not get confused
        between a registration number and a numeric patient_id.
        """
        logger.info(f"Generating answer for question: {question}")

        if not rows:
            return "I'm sorry, but no details were found in the database."

        # Filter out empty/null/audit fields to present clean text to LLM
        cleaned_rows = []
        audit_prefixes = ("inserted", "updated", "cancelled", "macid", "ipaddress")
        for row in rows[:30]:  # Cap at 30 rows to prevent payload bloat
            if isinstance(row, dict):
                clean_r = {}
                for k, v in row.items():
                    if v is None or v == "" or str(v).lower() in ("null", "none"):
                        continue
                    if any(k.lower().startswith(p) or k.lower().endswith(p) for p in audit_prefixes):
                        continue
                    if k.lower() in ("patient_id", "patientid"):
                        continue
                    # Truncate excessively long values to prevent payload bloat
                    str_v = str(v)
                    if len(str_v) > 200:
                        v = str_v[:200] + "..."
                    clean_r[k] = v
                
                cleaned_rows.append(clean_r)
            else:
                cleaned_rows.append(row)

        # Format records as clean plain text instead of raw JSON
        formatted_records = []
        for idx, r in enumerate(cleaned_rows, 1):
            if isinstance(r, dict):
                # Always put visit_no FIRST if it exists
                ordered = {}
                for vk in ("visit_no", "visitno"):
                    if vk in r and r[vk]:
                        ordered[vk] = r[vk]
                        break
                ordered.update({k: v for k, v in r.items() if k not in ("visit_no", "visitno")})
                fields_str = ", ".join(f"{k}: {v}" for k, v in ordered.items())
                formatted_records.append(f"Record {idx}: {fields_str}")
            else:
                formatted_records.append(f"Record {idx}: {r}")

        data_str = "\n".join(formatted_records)

        # Safety cap: if data_str is too large, truncate to prevent 413 errors
        MAX_DATA_CHARS = 3500
        if len(data_str) > MAX_DATA_CHARS:
            data_str = data_str[:MAX_DATA_CHARS] + "\n... (data truncated for brevity)"

        patient_line = ""
        if patient_context is not None:
            patient_line = (
                "\nPatient being queried (the doctor asked about THIS person):\n"
                f"- registration number: {getattr(patient_context, 'registration_no', '?')}\n"
                f"- internal numeric id used in the data rows: {getattr(patient_context, 'patient_id', '?')}\n"
                f"- name: {getattr(patient_context, 'name', '?')}\n"
                "The numeric id above is what appears as the patient's id in the Data."
            )

        prompt = f"""You are an expert EMR clinical assistant helping a doctor in a hospital.
Your task is to present the clinical details from the Data below directly to the physician.

CRITICAL INSTRUCTIONS:
- First and foremost, you MUST answer the user's Question directly.
- If the user asks for a simple summary, overview, or details, summarize the records in a clean markdown table.
- However, if the user explicitly asks for an explanation, evaluation, or comparison (e.g., "compare these drugs", "is it normal?", "what is this?"), you MUST provide a detailed clinical explanation or comparison based on the Data, followed by the table.
- CRITICAL RULE: If the user just asks to "show" or wants the "detail" of vitals or labs (e.g., "vitals detail", "show lab tests"), you MUST just present the plain data table. DO NOT evaluate it, and DO NOT add Normal Range or Assessment columns.
- ONLY IF the user explicitly asks an evaluative question (e.g., "is it normal?", "is anything dangerous?", "evaluate the vitals"), then you MUST format your evaluation as a markdown table. You MUST EXACTLY use these columns, even if the SQL didn't provide a normal range:
  1. Visit No (include this column if a visit number is present in the data)
  2. Date/Time (include this column if present in the data)
  3. Parameter (e.g. Systolic Blood Pressure)
  4. Normal Range (Use your medical knowledge to provide the standard reference range)
  5. Patient's Value (the reading from the database)
  6. Assessment (You MUST put BOTH the emoji and the text together, for example: "🟢 Normal", "🟠 Elevated", or "🔴 High/Dangerous". Do not just put the emoji by itself!)
- IF evaluating ALLERGIES, PRESCRIPTIONS, or SURGERIES, do NOT use a Normal Range table. Create a clinically appropriate, standard Markdown table comparing or summarizing the data without normal ranges.
- **VITALS TABLE FORMAT**: When displaying vitals data (blood pressure, temperature, pulse, etc.), you MUST use a NARROW/LONG table format with ONE ROW PER VITAL PARAMETER PER VISIT. Do NOT create a single wide row with all vitals as separate columns. Format like this:
  | Visit No | Date/Time | Parameter | Value |
  Example rows: Systolic BP = one row, Diastolic BP = another row, Temperature = another row, etc.
- **RADIOLOGY DETAILS**: If the Data contains an `html_template` column, you MUST include it exactly as-is in your markdown table without escaping the HTML tags.
- **CRITICAL LAB RESULTS**: If the Data contains a column like 'Critical', 'iscritical', 'paramhigh', 'paramlow' that indicates a result is abnormal, you MUST format the 'Result' value in the markdown table using HTML: `<span style='color:red; font-weight:bold;'>VALUE</span>`
- **PATIENT DEMOGRAPHICS**: When displaying patient details, you MUST format it as a landscape (wide) table where the fields (e.g., Patient ID, Name, Gender, DOB) are the column headers across the top, and the patient's data is in a single row below them. Do NOT use a vertical Field/Value format.
- **VISIT & DISCHARGE DETAILS**: Present visit and discharge details using clean, standard Markdown tables. Always ensure the most recent (last) visit appears FIRST.
- **CRITICAL LAB RESULTS**: If the Data contains a column like 'Critical', 'iscritical', 'paramhigh', 'paramlow' that indicates a result is abnormal, you MUST format the 'Result' value in the markdown table using HTML: `<span style='color:red; font-weight:bold;'>VALUE</span>`
- **NO EXTRA NOTES**: Do NOT append text like 'No additional visit, vitals, lab, or radiology records were returned for this patient' or 'Notes: No additional notes were provided'. Stick strictly to the data provided.
- **STRICT DATA ADHERENCE**: You MUST ONLY include records, tests, or items that are EXACTLY present in the Clinical Data provided. DO NOT hallucinate, infer, or add any items that are not explicitly listed in the rows below.
{patient_line}

Question: {question}
SQL Executed: {sql}

Clinical Data:
{data_str}

Clinical Summary:"""

        try:
            answer = self.llm.generate(prompt, model=ANSWER_MODEL, temperature=0.3)
            import re
            answer = re.sub(r"<(think|thought)>.*?</\\1>\n*", "", answer, flags=re.DOTALL | re.IGNORECASE)
            answer = re.sub(r"<(think|thought)>", "", answer, flags=re.IGNORECASE)
            answer = re.sub(r"</(think|thought)>", "", answer, flags=re.IGNORECASE)
            return answer.strip()
        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            return f"I found {len(rows)} matching records, but could not generate a summary."

    def generate_conversational(self, question: str, session_context: str = "") -> str:
        """Handles general chat without database access."""
        logger.info(f"Generating conversational answer for: {question}")
        prompt = f"""You are an expert EMR AI clinical assistant designed to help doctors analyze patient data.
You are currently chatting with a doctor. Answer their question politely and professionally.
3. If the doctor asks for post-operative care or post-care steps for a surgery/operation that the patient had, 
format the response with clear headings, use bullet points, and **bold** the most important keywords.
4. If the doctor asks to compare medications or drugs, you MUST use your medical knowledge to perform a real 
clinical/pharmacological comparison (e.g., uses, mechanism, side effects, contraindications) and present the 
comparison strictly as a concise Markdown table. If you do not recognize a specific brand name medication, you MUST 
NOT refuse. Instead, infer its pharmacological class or provide a general best-effort comparison using standard 
medical knowledge.
5. If the doctor asks you to write a letter, certificate, or clinical document, you MUST use the real patient and doctor details from the Chat History Context (like patient name, admission dates, doctor name) instead of generic placeholders like [Doctor Name]. DO NOT use Markdown formatting (like ** or #) in the final letter.

IMPORTANT GUARDRAIL: You are a strict EMR Patient Data assistant. Do NOT answer ANY general medical trivia or 
out-of-context drug comparisons. If the user asks a completely unrelated medical question (e.g., 'explain 
hypertension', 'how to make coffee'), you MUST politely refuse. HOWEVER, if the user asks you to explain or compare 
medications that the patient is currently taking (which you can see in the Chat History Context), you MUST provide a 
detailed clinical pharmacological comparison presented entirely in a concise Markdown table format. Do not hallucinate any information.

Chat History Context:
{session_context}

Doctor: {question}
Assistant:"""
        try:
            answer = self.llm.generate(prompt, model=ANSWER_MODEL, temperature=0.7)
            import re
            answer = re.sub(r"<(think|thought)>.*?</\1>\n*", "", answer, flags=re.DOTALL | re.IGNORECASE)
            answer = re.sub(r"<(think|thought)>", "", answer, flags=re.IGNORECASE)
            answer = re.sub(r"</(think|thought)>", "", answer, flags=re.IGNORECASE)
            return answer.strip()
        except Exception as e:
            logger.error(f"Conversational generation failed: {e}")
            return f"⚠️ **API Error:** I encountered an issue connecting to the AI provider. Please try again. ({e})"

    def generate_with_context(self, question: str, previous_clinical_data: str, session_context: str = "") -> str:
        """Handles evaluative follow-ups (e.g., 'is it normal?') by injecting previous clinical data.
        
        Uses normal_ranges.json for reference ranges — not LLM-generated values.
        Reverse-scans session history for the last VITALS/LAB turn (done by orchestrator).
        """
        logger.info(f"Generating evaluative answer with context for: {question}")
        
        prompt = f"""You are an expert EMR clinical assistant helping a doctor evaluate patient data.

The doctor previously viewed the following clinical data and is now asking a follow-up question about it.

### Previously Shown Clinical Data:
{previous_clinical_data}

### Doctor's Follow-up Question:
{question}

INSTRUCTIONS:
- You should provide a short, professional conversational summary evaluating the results (e.g., "Yes, a few parameters are abnormal...").
- Do NOT output your internal thinking or reasoning process blocks.
- After your short summary, you MUST format your detailed evaluation as a markdown table.
- Use your vast expert clinical knowledge to determine the standard Normal Range for each parameter.
- IF evaluating VITALS or LAB tests, you MUST STRICTLY use the following table format and column headers:
  | Visit No | Date/Time | Parameter | Normal Range | Patient's Value | Assessment |
  |---|---|---|---|---|---|
  * NOTE: The "Assessment" column MUST include BOTH an emoji and text (e.g., "🟢 Normal", "🟠 Elevated", or "🔴 High/Dangerous"). Do not just put the emoji by itself.
- IF evaluating ALLERGIES, PRESCRIPTIONS, or SURGERIES, do NOT output a Normal Range table. Instead, present a clinically appropriate, concise comparison or summary table suited to the data type.
- Create ONE ROW per individual vital sign/lab parameter per visit. Do NOT create wide tables.
- Include ALL parameters from the data — do not skip any.

Evaluation:"""
        try:
            answer = self.llm.generate(prompt, model=ANSWER_MODEL, temperature=0.3)
            import re
            answer = re.sub(r"<(think|thought)>.*?</\\1>\n*", "", answer, flags=re.DOTALL | re.IGNORECASE)
            answer = re.sub(r"<(think|thought)>", "", answer, flags=re.IGNORECASE)
            answer = re.sub(r"</(think|thought)>", "", answer, flags=re.IGNORECASE)
            return answer.strip()
        except Exception as e:
            logger.error(f"Evaluative answer generation failed: {e}")
            return "I could not generate the evaluation. Please try again."
