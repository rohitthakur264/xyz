from run_phase2 import execute_sql_pipeline

print("Running test...")
result = execute_sql_pipeline("registration no 165881")
import json
print("\n=== DEBUG INFO ===")
print(json.dumps(result.get("debug_info", {}), indent=2))
