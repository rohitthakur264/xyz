import ollama
from config.settings import ANSWER_MODEL, LLM_TEMPERATURE

def route_question(question: str) -> str:
    """
    Routes a standalone question to one of four categories:
    - DATABASE (for fresh database lookups of hospital records, patient data, schedules)
    - KNOWLEDGE (for protocols, medical knowledge, postcare guidelines)
    - CONTEXT_REASONING (for reasoning about, interpreting, or evaluating previously retrieved data, e.g., 'Is this visit recent?', 'What does this mean?')
    - OFF_TOPIC (for everything else or if unsure)
    """
    
    prompt = f"""
You are a routing assistant for a hospital AI.
Your job is to decide where to send the user's question.

Categories:
1. DATABASE: Questions requesting a fresh database lookup of specific patients, lab results, appointments, schedules, billing, or facts.
2. KNOWLEDGE: Questions about general medical protocols, postcare instructions, SOPs, or general medical knowledge.
3. CONTEXT_REASONING: Questions asking to explain, interpret, compare, or evaluate data previously shown/retrieved (e.g. 'Is this visit recent?', 'What does this lab result mean?', 'Are these vitals normal?').
4. OFF_TOPIC: Questions that do not fit the above, or are conversational.

Rules:
- Output EXACTLY one category name: DATABASE, KNOWLEDGE, CONTEXT_REASONING, or OFF_TOPIC.
- Do not output any punctuation, explanation, or extra text.

Question: {question}
"""

    allowed_outputs = {"DATABASE", "KNOWLEDGE", "CONTEXT_REASONING", "OFF_TOPIC"}
    
    def attempt_routing():
        response = ollama.chat(
            model=ANSWER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": LLM_TEMPERATURE}
        )
        return response['message']['content'].strip().upper()
    
    # First attempt
    result = attempt_routing()
    
    # Strip any stray punctuation just in case
    result = ''.join(char for char in result if char.isalpha() or char == '_')
    
    if result in allowed_outputs:
        return result
        
    # Retry once if it failed
    result_retry = attempt_routing()
    result_retry = ''.join(char for char in result_retry if char.isalpha() or char == '_')
    
    if result_retry in allowed_outputs:
        return result_retry
        
    # Default to OFF_TOPIC if it still doesn't match
    return "OFF_TOPIC"
