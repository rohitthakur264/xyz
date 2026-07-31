import os
import json
import uuid
import datetime
import uuid
from memory.session_store import load_session, add_turn
from memory.rewriter import rewrite_question
from router.intent_router import route_question
from run_phase2 import execute_sql_pipeline
from run_phase3 import execute_rag_pipeline

def run_phase6():
    print("=== Phase 6: Router and Full Pipeline ===")
    session_id = input("Enter a session ID (or press Enter for a new random one): ").strip()
    if not session_id:
        session_id = str(uuid.uuid4())[:8]
        
    print(f"\nStarted session: {session_id}")
    print("Type 'quit' to exit.")
    
    os.makedirs("logs", exist_ok=True)
    log_file = "logs/interaction_log.jsonl"
    
    while True:
        question = input(f"\n[{session_id}] You: ").strip()
        if question.lower() in ['quit', 'exit']:
            break
        if not question:
            continue
            
        # Memory / Rewriter
        history = load_session(session_id)
        rewritten = rewrite_question(question, history)
        
        if rewritten.startswith("AMBIGUOUS:"):
            print(f"\nAssistant: {rewritten}")
            print("Please clarify your question.")
            continue
            
        if rewritten != question:
            print(f"\n[Interpreted as: {rewritten}]")
            
        # Router
        route = route_question(rewritten)
        print(f"[Routed to: {route}]")
        
        # Pipeline execution
        final_answer = ""
        source_used = None
        
        if route == "DATABASE":
            result = execute_sql_pipeline(rewritten)
            final_answer = result["answer"]
            source_used = "sql" if result.get("sql_used") else "none"
        elif route == "KNOWLEDGE":
            result = execute_rag_pipeline(rewritten)
            final_answer = result["answer"]
            
            # Extract document names for source_used if available
            verified_chunks = result.get("verified_chunks", [])
            if verified_chunks:
                sources = list(set(chunk['metadata'].get('source_file', 'unknown') for chunk in verified_chunks))
                source_used = "document:" + ",".join(sources)
            else:
                source_used = "general_fallback"
        else: # OFF_TOPIC
            final_answer = "I can only answer questions related to the hospital database or medical knowledge base."
            source_used = "off_topic"
            
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
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

if __name__ == "__main__":
    run_phase6()
