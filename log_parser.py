import json

try:
    lines = open('logs/interaction_log.jsonl').readlines()
    print("--- LATEST TEST ERRORS ---")
    for line in lines[-15:]:
        try:
            d = json.loads(line)
            if 'ui_test' in d.get('session_id', ''):
                debug = d.get('debug_info', {})
                if debug and debug.get('attempts'):
                    print(f"\nQ: {d.get('raw_question')}")
                    for i, att in enumerate(debug['attempts']):
                        print(f"  Attempt {i+1} SQL: {att.get('sql')[:150]}")
                        print(f"  Attempt {i+1} Err: {att.get('error')}")
        except Exception:
            pass
except Exception as e:
    print(f"Error reading logs: {e}")
