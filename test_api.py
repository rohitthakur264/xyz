import requests
import uuid

API_URL = "http://localhost:8000/chat"

def print_resp(title, resp):
    print(f"--- {title} ---")
    print(f"Question: {resp['rewritten_question']}")
    print(f"Answer: {resp['answer']}")
    print(f"Route: {resp['route_decision']}")
    print()

def test():
    session_id = str(uuid.uuid4())[:8]
    
    print(f"=== Starting Session: {session_id} ===\n")
    
    # 1. Initial Resolution Test
    resp1 = requests.post(API_URL, json={"question": "registration no 165881", "session_id": session_id}).json()
    print_resp("TEST 1: Initial Resolution (165881)", resp1)
    
    # 2. Follow-up Join Elimination Test (vitals) & 3. Rewriter Interference Test
    resp2 = requests.post(API_URL, json={"question": "show vitals", "session_id": session_id}).json()
    print_resp("TEST 2/3: Join Elimination & No Rewriter ID Insertion", resp2)
    
    # 3. Ambiguous Name Match
    resp3 = requests.post(API_URL, json={"question": "show allergy for ALI", "session_id": session_id}).json()
    print_resp("TEST 4: Ambiguous Name Match", resp3)
    
    # 4. Patient Not Found
    resp4 = requests.post(API_URL, json={"question": "show billing for fakeid99999", "session_id": session_id}).json()
    print_resp("TEST 5: Patient Not Found", resp4)
    
    # 5. Mid-conversation Switch
    resp5 = requests.post(API_URL, json={"question": "show vitals for patient id 12345", "session_id": session_id}).json()
    print_resp("TEST 6: Mid-conversation Switch", resp5)
    
    resp6 = requests.post(API_URL, json={"question": "show allergy", "session_id": session_id}).json()
    print_resp("TEST 7: Stickiness on New Patient", resp6)

if __name__ == "__main__":
    test()
