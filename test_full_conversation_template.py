import requests
import json

API_URL = "http://localhost:8000/chat"

turns = [
    "registration no 165881",
    "Show last visit",
    "What tests were prescribed to the patient in his last visit",
    "Show the results of this test",
    "What medicines were earlier prescribed?",
    "What are the uses for the first medicine?",
    "And what about the second medicine?",
    "Any surgeries conducted for this patient",
    "Explain the details of this surgery",
    "Does the patient have any allergies?",
    "Show patient vitals",
    "Any of these parameters are not in the normal range?",
    "What orders are given to the patient?",
    "Get all visit details"
]

def run_test():
    session_id = "test_template_session_100"
    print("=== Starting Full Conversation Template Test ===")
    for i, t in enumerate(turns):
        print(f"\n--- Turn {i+1}: '{t}' ---")
        try:
            res = requests.post(API_URL, json={"question": t, "session_id": session_id}, timeout=120)
            res.raise_for_status()
            data = res.json()
            print("Answer:", data.get("answer"))
            print(f"Source: {data.get('source_used')}, Route: {data.get('route_decision')}")
            assert data.get("route_decision") != "ERROR", f"Turn {i+1} failed with ERROR route!"
        except Exception as e:
            print(f"Error on turn {i+1}: {e}")
            raise e

if __name__ == "__main__":
    run_test()
