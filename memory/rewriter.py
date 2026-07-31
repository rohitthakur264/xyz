import ollama
from config.settings import ANSWER_MODEL, LLM_TEMPERATURE

def rewrite_question(new_question, history):
    """
    Takes a new question and a list of historical turns (dicts with 'q' and 'a').
    Returns a standalone rewritten question, or 'AMBIGUOUS: <reason>' if it cannot be safely resolved.
    """
    if not history:
        return new_question
        
    history_text = ""
    for i, turn in enumerate(history[-3:]):  # only use last 3 turns
        history_text += f"Turn {i+1}:\nUser: {turn['q']}\nAssistant: {turn['a']}\n\n"
        
    system_prompt = (
        "You are an expert conversational query rewriter for a medical database assistant.\n"
        "Your task is to take the user's latest follow-up question and rewrite it into a fully standalone question "
        "that contains all necessary context from the conversation history.\n\n"
        "RULES:\n"
        "1. If the latest question is already completely standalone and doesn't rely on history (e.g., 'What are the visiting hours?'), DO NOT add unnecessary historical context. Just return the question as-is.\n"
        "2. If the question uses pronouns ('it', 'this', 'that visit', 'these results', 'those labs') or asks to interpret previously shown data ('is this normal?', 'what does this mean?'), preserve the reference to the dataset/results from the immediate previous turn.\n"
        "3. CRITICAL: If the history mentions multiple possible referents (e.g. two different patients) and the new question is ambiguous (e.g. 'what about his labs?'), DO NOT GUESS. Instead, return EXACTLY: 'AMBIGUOUS: <reason why it is ambiguous>'.\n"
        "4. DO NOT answer the question. Only output the rewritten question or the AMBIGUOUS string.\n"
        "5. DO NOT inject patient names, IDs, or registration numbers into the rewritten question from the history unless explicitly necessary for clarity. Preserve the clinical interpretation intent."
    )
    
    user_content = f"History:\n{history_text}\nLatest Question: {new_question}"
    
    try:
        response = ollama.chat(
            model=ANSWER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            options={'temperature': LLM_TEMPERATURE}
        )
        return response['message']['content'].strip()
    except Exception as e:
        print(f"Error calling LLM for rewrite: {e}")
        return new_question
