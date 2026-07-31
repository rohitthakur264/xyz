import os
import json
import uuid
import datetime
from memory.session_store import load_session, add_turn
from memory.rewriter import rewrite_question
from router.intent_router import route_question
from run_phase2 import execute_sql_pipeline
from run_phase3 import execute_rag_pipeline
from guardrails.verifier import verify_answer
from config.settings import INTERACTION_LOG_FILE

def run_phase7():
    print("=== Phase 7: Full Pipeline with Guardrails ===")
    session_id = input("Enter a session ID (or press Enter for a new random one): ").strip()
    if not session_id:
        session_id = str(uuid.uuid4())[:8]
        
    print(f"\nStarted session: {session_id}")
    print("Type 'quit' to exit.")
    
    os.makedirs(os.path.dirname(INTERACTION_LOG_FILE), exist_ok=True)
    
    while True:
        question = input(f"\n[{session_id}] You: ").strip()
        if question.lower() in ['quit', 'exit']:
            break
        if not question:
            continue
            
        # 1. Memory / Rewriter
        history = load_session(session_id)
        rewritten = rewrite_question(question, history)
        
        if rewritten.startswith("AMBIGUOUS:"):
            print(f"\nAssistant: {rewritten}")
            print("Please clarify your question.")
            continue
            
        if rewritten != question:
            print(f"\n[Interpreted as: {rewritten}]")
            
        # 2. Router
        route = route_question(rewritten)
        print(f"[Routed to: {route}]")
        
        # 3. Pipeline execution
        final_answer = ""
        source_used = None
        retrieved_context = "" # Used for the verifier
        
        if route == "DATABASE":
            result = execute_sql_pipeline(rewritten)
            final_answer = result["answer"]
            source_used = "sql" if result.get("sql_used") else "none"
            # Format the DB rows/SQL for the verifier
            if result.get("sql_used"):
                rows = result.get('rows', [])
                cols = result.get('columns', [])
                if not rows:
                    data_str = "No results found."
                else:
                    data_str = " | ".join(cols) + "\n"
                    for row in rows:
                        data_str += " | ".join([str(val) for val in row]) + "\n"
                retrieved_context = f"SQL Executed: {result.get('sql_used')}\nResults Data:\n{data_str}"
                
                # Store last_result
                from memory.session_store import set_last_result
                set_last_result(session_id, {
                    "sql": result.get("sql_used"),
                    "rows": rows,
                    "columns": cols,
                    "formatted_data": data_str,
                    "question": rewritten
                })

        elif route == "CONTEXT_REASONING":
            from memory.session_store import get_last_result
            from sql_pipeline.answerer import answer_reasoning_question
            last_result = get_last_result(session_id)
            if last_result and last_result.get("formatted_data"):
                final_answer = answer_reasoning_question(rewritten, last_result)
                source_used = "context_reasoning"
                retrieved_context = f"Last Result Context:\n{last_result.get('formatted_data', '')}"
            else:
                final_answer = "No previous query data is available in your current session to interpret. Please ask a specific lookup question first."
                source_used = "context_reasoning_missing"
                
        elif route == "KNOWLEDGE":
            result = execute_rag_pipeline(rewritten)
            final_answer = result["answer"]
            
            verified_chunks = result.get("verified_chunks", [])
            if verified_chunks:
                sources = list(set(chunk['metadata'].get('source_file', 'unknown') for chunk in verified_chunks))
                source_used = "document:" + ",".join(sources)
                retrieved_context = "\n".join([c["text"] for c in verified_chunks])
            else:
                source_used = "general_fallback"
                
        else: # OFF_TOPIC
            final_answer = "I can only answer questions related to the hospital database or medical knowledge base."
            source_used = "off_topic"
            
        # 4. Final Verifier Pass (Guardrails)
        # We only verify if we actually retrieved data (not a fallback or off_topic)
        if retrieved_context:
            final_answer, verifier_verdict, _ = verify_answer(rewritten, final_answer, retrieved_context)
            if verifier_verdict != "SUPPORTED" and verifier_verdict != "NO_CONTEXT_NEEDED":
                print(f"[Verifier flagged answer: {verifier_verdict}]")
            
        print(f"\nAssistant: {final_answer}")
        
        # Add to session history
        add_turn(session_id, question, final_answer)
        
        # Append to interaction log
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "session_id": session_id,
            "raw_question": question,
            "rewritten_question": rewritten,
            "route_decision": route,
            "pipeline_output": final_answer,
            "source_used": source_used
        }
        with open(INTERACTION_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

if __name__ == "__main__":
    run_phase7()
