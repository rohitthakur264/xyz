import os
import json
import ollama
from config.settings import ANSWER_MODEL, LLM_TEMPERATURE
from config.prompts import MASTER_SYSTEM_PROMPT
from datetime import datetime

# FALLBACK_LOG removed: handled by interaction log in Phase 6/7

def generate_answer(question, verified_chunks):
    """
    Generates the final answer. 
    If verified_chunks is empty, provides a fallback answer.
    """
    if not verified_chunks:
        system_prompt = MASTER_SYSTEM_PROMPT + "\n\n=== TASK: GENERAL MEDICAL REFERENCE (FALLBACK) ===\n"
        system_prompt += (
            "The hospital protocols do not contain the answer to the user's question.\n"
            "Provide a general medical reference answer, but per Rule 15 you MUST start your response exactly with this warning:\n"
            "'⚠️ General medical reference — not verified against this hospital\\'s records or protocols.'"
        )
        try:
            response = ollama.chat(
                model=ANSWER_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question}
                ],
                options={'temperature': LLM_TEMPERATURE}
            )
            return response['message']['content'].strip()
        except Exception as e:
            return f"Error generating fallback answer: {e}"

    # If we have chunks, build context and generate grounded answer
    context = ""
    citations = set()
    for i, chunk in enumerate(verified_chunks):
        source = chunk['metadata'].get('source_file', 'Unknown')
        page = chunk['metadata'].get('page_number', 'Unknown')
        citations.add(f"{source}, Page {page}")
        context += f"--- Document {i+1} ---\n{chunk['text']}\n\n"
        
    system_prompt = MASTER_SYSTEM_PROMPT + "\n\n=== TASK: PROTOCOL DOCUMENT RAG ANSWER ===\n"
    system_prompt += (
        "Answer the user's question using ONLY the provided document passages.\n"
        "Do not use outside knowledge. If the passages do not fully answer the question, state that clearly."
    )
    
    try:
        response = ollama.chat(
            model=ANSWER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context passages:\n{context}\n\nQuestion: {question}"}
            ],
            options={'temperature': LLM_TEMPERATURE}
        )
        
        answer = response['message']['content'].strip()
        
        # Append citations
        answer += "\n\n**Sources Cited:**\n"
        for c in citations:
            answer += f"- {c}\n"
            
        return answer
        
    except Exception as e:
        return f"Error generating grounded answer: {e}"
