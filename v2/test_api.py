import requests

url = "http://localhost:8001/chat"
session_id = "test_session_123"
doctor_id = "doc_test_1"

questions = [
    "what are the visit details for registration no 166637",
    "allergies for 166637",
    "vitals for 166637",
    "family history for 166637"
]

for q in questions:
    print(f"\n--- Question: {q} ---")
    payload = {
        "session_id": session_id,
        "doctor_id": doctor_id,
        "question": q
    }
    resp = requests.post(url, json=payload)
    if resp.status_code == 200:
        data = resp.json()
        print("Intent:", data.get("intent"))
        print("Answer preview:", str(data.get("answer"))[:200])
        print("SQL Executed:\n", data.get("sql"))
        
        raw_data = data.get("raw_data")
        if raw_data:
            print("Raw Data (Rows returned):", len(raw_data))
        else:
            print("Raw Data: None")
    else:
        print("Error:", resp.text)
