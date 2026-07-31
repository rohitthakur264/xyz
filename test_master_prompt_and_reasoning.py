import json
from config.settings import SQL_MODEL, ANSWER_MODEL
from config.prompts import MASTER_SYSTEM_PROMPT
from memory.session_store import load_session, add_turn, set_last_result, get_last_result
from router.intent_router import route_question
from memory.rewriter import rewrite_question
from sql_pipeline.answerer import answer_reasoning_question

def test_pipeline():
    print("=== Test 1: Config & Prompts Check ===")
    print(f"SQL_MODEL: {SQL_MODEL}")
    print(f"ANSWER_MODEL: {ANSWER_MODEL}")
    assert len(MASTER_SYSTEM_PROMPT) > 500
    print("MASTER_SYSTEM_PROMPT loaded successfully. Length:", len(MASTER_SYSTEM_PROMPT))
    print("Test 1 Passed!\n")

    print("=== Test 2: Session Store & Migration Safety ===")
    test_sid = "test_session_999"
    sdata = load_session(test_sid)
    assert sdata.get("last_result") is None
    set_last_result(test_sid, {
        "sql": "SELECT * FROM fhir_patient_mst LIMIT 1",
        "rows": [["180267", "165881", "MARAD"]],
        "columns": ["id", "registration_no", "display"],
        "formatted_data": "id | registration_no | display\n180267 | 165881 | MARAD\n",
        "question": "show me patient 165881"
    })
    last_res = get_last_result(test_sid)
    assert last_res is not None
    assert last_res["rows"][0][0] == "180267"
    print("Session store last_result verified!")
    print("Test 2 Passed!\n")

    print("=== Test 3: Router CONTEXT_REASONING Check ===")
    r1 = route_question("Is this visit recent?")
    print(f"Route for 'Is this visit recent?': {r1}")
    assert r1 in ["CONTEXT_REASONING", "DATABASE"]
    print("Test 3 Passed!\n")

    print("=== Test 4: Answer Reasoning Function Check ===")
    reasoning_ans = answer_reasoning_question("Is this patient's registration number 165881?", last_res)
    print("Reasoning Answer:")
    print(reasoning_ans)
    assert "165881" in reasoning_ans or "MARAD" in reasoning_ans or "database" in reasoning_ans.lower()
    print("Test 4 Passed!\n")

if __name__ == "__main__":
    test_pipeline()
