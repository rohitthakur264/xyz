from api.main import chat_endpoint
from api.models import ChatRequest

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

def run_direct_test():
    session_id = "test_template_direct_200"
    print("=== Starting Direct 14-Turn Conversation Template Test ===")
    for i, t in enumerate(turns):
        print(f"\n==========================================")
        print(f"Turn {i+1}: '{t}'")
        req = ChatRequest(question=t, session_id=session_id)
        res = chat_endpoint(req)
        print(f"Route: {res.route_decision} | Source: {res.source_used}")
        print(f"Rewritten: {res.rewritten_question}")
        print(f"Answer:\n{res.answer}")
        assert res.route_decision != "ERROR", f"Turn {i+1} failed with ERROR!"

if __name__ == "__main__":
    run_direct_test()
