import os
import json
from run_phase2 import execute_sql_pipeline
from memory.session_store import set_active_patient

active_patient = {
    "id": 180267,
    "registration_no": "165881",
    "display": "MARAD"
}

questions = [
    "visit detail",
    "billing dtl",
    "vitals dtl",
    "allergy dtl",
    "prescription dtl",
    "operation"
]

print("=== Testing SQL Generation with New Prompt ===")
for q in questions:
    print(f"\n--- Q: {q} ---")
    try:
        res = execute_sql_pipeline(q, active_patient=active_patient)
        if res.get("sql_used"):
            print(f"SQL: {res['sql_used']}")
            print(f"Rows: {len(res.get('rows', []))}")
        else:
            print(f"No SQL used. Error: {res.get('error')}")
            if res.get('debug_info', {}).get('attempts'):
                print("Attempts:")
                for att in res['debug_info']['attempts']:
                    print(f"  Attempt {att['attempt']}: SQL={att.get('sql')} | Result={att.get('result')}")
    except Exception as e:
        print(f"Exception: {e}")
