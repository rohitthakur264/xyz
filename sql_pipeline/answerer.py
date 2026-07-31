import ollama
from config.settings import ANSWER_MODEL, LLM_TEMPERATURE
from config.prompts import MASTER_SYSTEM_PROMPT

def answer_question(question, sql_used, columns, rows):
    """
    Feeds the executed SQL rows back to the LLM to generate a natural language answer.
    """
    if rows is None:
        return "I couldn't safely answer this from the database."

    if not rows:
        data_context = "No results found."
    else:
        data_context = " | ".join(columns) + "\n"
        for row in rows:
            data_context += " | ".join([str(val) for val in row]) + "\n"
            
    system_prompt = MASTER_SYSTEM_PROMPT + "\n\n=== TASK: DATA RESPONSE FORMATTING ===\n"
    system_prompt += (
        "Format the answer to the user's question based strictly on the provided Results Data.\n"
        "Follow Rules 12-16 strictly for formatting:\n"
        "- Single record/lookup: short labeled summary block (field: value).\n"
        "- Multi-row results: render as an actual markdown table.\n"
        "- Single value: direct short sentence.\n"
        "Traceability: State plainly that records came from database records."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Results Data:\n{data_context}\n\nQuestion: {question}"}
    ]

    try:
        response = ollama.chat(
            model=ANSWER_MODEL,
            messages=messages,
            options={'temperature': LLM_TEMPERATURE}
        )
        return response['message']['content'].strip()
    except Exception as e:
        return f"Error generating final answer: {e}"

def answer_reasoning_question(question, last_result):
    """
    Handles follow-up reasoning/interpretation questions about previously retrieved data (last_result).
    Does NOT execute a new SQL query.
    """
    if not last_result or not last_result.get("formatted_data"):
        return "No previous query data is available in the current context to reason about. Please run a new lookup question first."

    data_context = last_result["formatted_data"]
    prev_question = last_result.get("question", "previous query")

    system_prompt = MASTER_SYSTEM_PROMPT + "\n\n=== TASK: CONTEXT REASONING & INTERPRETATION ===\n"
    system_prompt += (
        "The doctor is asking a follow-up question to interpret or reason about the previously retrieved dataset.\n"
        "Use the Last Result Context provided below directly to answer the question.\n"
        "Follow Rule 6 and Rules 14-16:\n"
        "- Evaluate the data directly against clinical/factual norms.\n"
        "- If general medical reference is needed for interpretation, include the disclaimer per Rule 15:\n"
        "  '⚠️ General medical reference — not verified against this hospital\\'s records or protocols.'\n"
        "- State plainly whether information came from the retrieved database records or general reference."
    )

    user_content = f"Last Result Context (from question: '{prev_question}'):\n{data_context}\n\nFollow-up Question: {question}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

    try:
        response = ollama.chat(
            model=ANSWER_MODEL,
            messages=messages,
            options={'temperature': LLM_TEMPERATURE}
        )
        return response['message']['content'].strip()
    except Exception as e:
        return f"Error interpreting previous results: {e}"
