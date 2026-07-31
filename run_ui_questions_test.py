import requests
import json
import uuid

API_URL = "http://localhost:8000/chat"

questions = [
    "registration no 165881",
    "visit detail",
    "billing dtl",
    "vitals dtl",
    "allergy dtl",
    "prescription dtl",
    "operation",
    "Is this operation recent and what does it mean?"
]

def run_test():
    session_id = f"ui_test_{str(uuid.uuid4())[:6]}"
    print(f"=== Running Full UI Questions Test Sequence (Session: {session_id}) ===\n")
    
    for i, q in enumerate(questions):
        print(f"==================================================")
        print(f"[{i+1}/{len(questions)}] User: {q}")
        try:
            res = requests.post(API_URL, json={"question": q, "session_id": session_id}, timeout=300)
            res.raise_for_status()
            data = res.json()
            
            print(f"Rewritten : {data.get('rewritten_question')}")
            print(f"Route     : {data.get('route_decision')} | Source: {data.get('source_used')}")
            print(f"Answer    :\n{data.get('answer')}")
            
            debug = data.get("debug") or {}
            
            # Print all debug fields we care about
            if debug.get("verifier_context"):
                ctx = debug["verifier_context"]
                # Show first 600 chars of context (has SQL + row data)
                print(f"\nDB Context (first 600 chars):\n{str(ctx)[:600]}")

            if debug.get("attempts"):
                print(f"\nAttempts ({len(debug['attempts'])}):")
                for att in debug["attempts"]:
                    print(f"  [{att.get('attempt')}] SQL: {str(att.get('sql',''))[:200]}")
                    print(f"        Result: {str(att.get('result',''))[:150]}")

            if debug.get("verifier_verdict"):
                print(f"\nVerifier: {debug['verifier_verdict']}")
                
        except Exception as e:
            print(f"ERROR on question '{q}': {e}")
        
        print()
            
    print("==================================================")
    print("=== Test Sequence Completed ===")

if __name__ == "__main__":
    run_test()
