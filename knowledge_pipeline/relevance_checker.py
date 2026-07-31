import ollama
from config.settings import LLM_MODEL, LLM_TEMPERATURE

def filter_relevant_chunks(question, candidate_chunks):
    """
    Takes candidate chunks from the retriever and asks the LLM to verify
    if the chunk ACTUALLY answers the question.
    Returns only the chunks that pass verification.
    """
    verified_chunks = []
    
    for chunk in candidate_chunks:
        system_prompt = (
            "You are a strict relevance verifier. You will be given a user's question and a passage of text. "
            "Does the passage contain the answer to the user's question? "
            "Answer ONLY with 'Yes' or 'No'."
        )
        
        user_content = f"Question: {question}\n\nPassage:\n{chunk['text']}"
        
        try:
            response = ollama.chat(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                options={'temperature': LLM_TEMPERATURE}
            )
            
            verdict = response['message']['content'].strip().lower()
            if 'yes' in verdict:
                verified_chunks.append(chunk)
                
        except Exception as e:
            print(f"Error during relevance check: {e}")
            
    return verified_chunks
