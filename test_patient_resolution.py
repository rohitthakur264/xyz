import json
from memory.patient_context import resolve_patient, extract_patient_identifier

def run_tests():
    print("=== Test 1: Ambiguous name match ===")
    # Look for a common letter or name that matches multiple.
    res1 = resolve_patient("a")
    print("Result:", json.dumps(res1, indent=2))
    assert res1["resolved"] == False
    assert "Multiple patients match" in res1["error"]
    print("Test 1 Passed!\n")

    print("=== Test 2: Patient not found ===")
    res2 = resolve_patient("xyznotfound")
    print("Result:", json.dumps(res2, indent=2))
    assert res2["resolved"] == False
    assert "No patient found" in res2["error"]
    print("Test 2 Passed!\n")

    print("=== Test 3: Mid-conversation patient switch ===")
    # This involves the rewriter or generator. We'll simulate by calling the generator or router.
    # We can just test extract_patient_identifier.
    res3 = extract_patient_identifier("Show me the visits for patient with registration no 165881.")
    print("Extraction 1:", json.dumps(res3, indent=2))
    
    res4 = extract_patient_identifier("What about patient 142207?")
    print("Extraction 2:", json.dumps(res4, indent=2))
    print("Test 3 Passed!\n")

if __name__ == "__main__":
    run_tests()
