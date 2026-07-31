from memory.patient_context import extract_patient_identifier, get_patient_details
from sql_pipeline.answerer import answer_question

def test():
    print("=== Testing Deterministic Patient Master Resolver ===")
    ctx = extract_patient_identifier("registration no 165881")
    print("Extracted context:", ctx)
    assert ctx["has_identifier"] == True
    patient = ctx["patient"]
    assert patient["id"] == 180267

    print("Fetching patient master details deterministically...")
    p_details = get_patient_details(patient["id"])
    print("Columns:", p_details["columns"])
    print("Rows:", p_details["rows"])
    assert len(p_details["rows"]) == 1

    formatted_answer = answer_question("registration no 165881", p_details["sql_used"], p_details["columns"], p_details["rows"])
    print("\nFormatted Labeled Summary Answer:")
    print(formatted_answer)
    assert "165881" in formatted_answer or "MARAD" in formatted_answer
    print("\nDeterministic Patient Master Lookup Passed!")

if __name__ == "__main__":
    test()
