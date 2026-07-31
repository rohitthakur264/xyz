import ollama
from config.settings import ANSWER_MODEL, LLM_TEMPERATURE

def verify_answer(question: str, drafted_answer: str, retrieved_context: str) -> tuple[str, str, str]:
    """
    Final verifier pass: checks if the drafted_answer is fully supported by the retrieved_context.
    If it is, returns (drafted_answer, 'SUPPORTED', retrieved_context).
    If not, returns a fallback warning along with the verdict.
    """
    # If there's no context, it's either a fallback or an off-topic answer, which we allow 
    # to pass through (assuming the pipelines already flagged them appropriately).
    if not retrieved_context.strip():
        return drafted_answer, "NO_CONTEXT_NEEDED", retrieved_context
        
    prompt = f"""
You are a strict fact-checking auditor for a hospital.
Your job is to verify if the drafted answer is FULLY SUPPORTED by the provided context.

Context:
{retrieved_context}

Drafted Answer:
{drafted_answer}

Question:
{question}

Rules:
1. If the Drafted Answer contains ANY factual claims, numbers, dates, or summary assertions (e.g., date ranges, counts) not directly present or verifiable in the Context, respond with exactly: UNSUPPORTED: <specific claim, quoted>
2. You MUST NOT penalize the answer for basic formatting, synthesizing columns (like combining first and last names), or adding polite conversational framing (e.g. "Here are the patient details:").
3. If the Drafted Answer's factual claims are supported by the Context, respond with exactly: SUPPORTED
"""

    try:
        response = ollama.chat(
            model=ANSWER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": LLM_TEMPERATURE}
        )
        
        result = response['message']['content'].strip()
        verdict_check = result.upper()
        
        if verdict_check.startswith("SUPPORTED"):
            return drafted_answer, "SUPPORTED", retrieved_context
        else:
            return "[WARNING: The generated answer contained unverified claims and was blocked. Please consult official hospital records.]", result, retrieved_context
            
    except Exception as e:
        return f"[WARNING: Error during verification pass: {e}]", f"ERROR: {e}", retrieved_context
