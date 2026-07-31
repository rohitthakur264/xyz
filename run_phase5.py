import uuid
from memory.session_store import load_session, add_turn
from memory.rewriter import rewrite_question

def run_phase5():
    print("=== Phase 5: Conversational Memory Dry-Run ===")
    print("Note: In Phase 8/9, session_id will be mapped to a logged-in doctor's authentication.")
    session_id = input("Enter a session ID (or press Enter for a new random one): ").strip()
    if not session_id:
        session_id = str(uuid.uuid4())[:8]
        
    print(f"\nStarted session: {session_id}")
    print("Type 'quit' to exit.")
    
    while True:
        question = input(f"\n[{session_id}] You: ").strip()
        if question.lower() in ['quit', 'exit']:
            break
        if not question:
            continue
            
        history = load_session(session_id)
        
        # Rewrite based on history
        rewritten = rewrite_question(question, history)
        
        if rewritten.startswith("AMBIGUOUS:"):
            print(f"\nAssistant: {rewritten}")
            print("Please clarify your question.")
            continue
            
        if rewritten != question:
            print(f"\n[Interpreted as: {rewritten}]")
            
        # Simulate an answer for the dry run
        dummy_answer = f"(Dummy Answer to: {rewritten})"
        print(f"Assistant: {dummy_answer}")
        
        add_turn(session_id, question, dummy_answer)

if __name__ == "__main__":
    run_phase5()
