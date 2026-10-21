"""
Smoke test for the ui/app.py vitals-graph rendering fix.

Verifies:
  1. When intent is the comma-joined multi-intent string "VITALS,BILLING"
     (as chat_orchestrator.py actually produces whenever >1 intent is
     detected in a turn), the vitals chart section STILL renders. This is
     the exact bug: the old code used `intent == "VITALS"` which fails for
     any multi-intent turn.
  2. Plain single-intent "VITALS" still renders (no regression).
  3. Intents that don't include VITALS (e.g. "BILLING") do NOT render the
     vitals section and, critically, do NOT crash the page.
  4. No exception is raised during any of the above renders.

This uses Streamlit's built-in AppTest harness to actually execute app.py
end-to-end (real Streamlit + real Altair chart building) against a mocked
session_state — no FastAPI backend, MySQL, or Ollama required.

Run with:
    cd v2
    python -m pytest tests/smoke/test_vitals_graph_smoke.py -v
or directly:
    python tests/smoke/test_vitals_graph_smoke.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DB_NAME", "smoke_test_db")

from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "ui", "app.py")

# Sample vitals rows shaped like what chat_orchestrator._clean_raw_data() /
# the report_schema.json "vitals" section actually produces.
SAMPLE_VITALS_RAW_DATA = [
    {
        "Vitals Datetime": "2026-08-01 09:00:00",
        "Systolic BP": 122,
        "Diastolic BP": 80,
        "Temperature": 36.8,
        "Pulse": 76,
        "Respiratory": 16,
        "Visit No": "V1001",
    },
    {
        "Vitals Datetime": "2026-08-05 09:00:00",
        "Systolic BP": 130,
        "Diastolic BP": 85,
        "Temperature": 37.5,
        "Pulse": 88,
        "Respiratory": 18,
        "Visit No": "V1002",
    },
    {
        "Vitals Datetime": "2026-08-10 09:00:00",
        "Systolic BP": 118,
        "Diastolic BP": 76,
        "Temperature": 36.9,
        "Pulse": 72,
        "Respiratory": 15,
        "Visit No": "V1003",
    },
]


def _seed_message(at: AppTest, intent: str, raw_data=None):
    """Seed session_state exactly the way app.py expects after a /chat call."""
    at.session_state["session_id"] = "session_smoketest"
    at.session_state["api_key"] = "doc_key_abc123"
    at.session_state["active_patient"] = {"name": "Test Patient", "reg_no": "REG-001", "id": "P001"}
    at.session_state["messages"] = [
        {"role": "user", "content": "show me vitals and billing"},
        {
            "role": "assistant",
            "content": "Here are the details.",
            "metadata": {"intent": intent, "tables_used": [], "sql_executed": ""},
            "raw_data": raw_data,
            "intent": intent,
        },
    ]


def _chart_titles_present(at: AppTest):
    md_values = [m.value for m in at.markdown]
    return any("Patient Vitals Trends" in v for v in md_values)


def run():
    failures = []

    # --- Case 1: THE BUG. Multi-intent string containing VITALS. ---
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    _seed_message(at, intent="VITALS,BILLING", raw_data=SAMPLE_VITALS_RAW_DATA)
    at.run()
    if at.exception:
        failures.append(f"[CRASH] multi-intent 'VITALS,BILLING' case raised: {at.exception[0].value}")
    elif not _chart_titles_present(at):
        failures.append("[REGRESSION] multi-intent 'VITALS,BILLING' did NOT render the vitals chart "
                         "(this is the exact bug that was reported)")
    else:
        print("OK  intent='VITALS,BILLING' -> vitals chart rendered")

    # --- Case 2: single intent 'VITALS' (no regression check). ---
    at2 = AppTest.from_file(APP_PATH, default_timeout=30)
    _seed_message(at2, intent="VITALS", raw_data=SAMPLE_VITALS_RAW_DATA)
    at2.run()
    if at2.exception:
        failures.append(f"[CRASH] single-intent 'VITALS' case raised: {at2.exception[0].value}")
    elif not _chart_titles_present(at2):
        failures.append("[REGRESSION] single-intent 'VITALS' did NOT render the vitals chart")
    else:
        print("OK  intent='VITALS' -> vitals chart rendered")

    # --- Case 3: BILLING only -> chart must NOT render, and must NOT crash. ---
    at3 = AppTest.from_file(APP_PATH, default_timeout=30)
    _seed_message(at3, intent="BILLING", raw_data=[{"Invoice No": "INV1", "Amount": 500}])
    at3.run()
    if at3.exception:
        failures.append(f"[CRASH] 'BILLING' only case raised: {at3.exception[0].value}")
    elif _chart_titles_present(at3):
        failures.append("[UNEXPECTED] 'BILLING' only case rendered a vitals chart (shouldn't)")
    else:
        print("OK  intent='BILLING' -> no vitals chart, no crash")

    # --- Case 4: VITALS with reversed multi-intent order (BILLING,VITALS). ---
    at4 = AppTest.from_file(APP_PATH, default_timeout=30)
    _seed_message(at4, intent="BILLING,VITALS", raw_data=SAMPLE_VITALS_RAW_DATA)
    at4.run()
    if at4.exception:
        failures.append(f"[CRASH] 'BILLING,VITALS' case raised: {at4.exception[0].value}")
    elif not _chart_titles_present(at4):
        failures.append("[REGRESSION] 'BILLING,VITALS' (VITALS not first) did NOT render the vitals chart")
    else:
        print("OK  intent='BILLING,VITALS' -> vitals chart rendered")

    print()
    if failures:
        print(f"FAILED: {len(failures)} issue(s) found")
        for f in failures:
            print("  -", f)
    else:
        print("PASSED: all 4 cases OK")
    return failures


def test_vitals_graph_smoke():
    """pytest entry point."""
    failures = run()
    assert not failures, f"{len(failures)} smoke test case(s) failed: {failures}"


if __name__ == "__main__":
    failures = run()
    sys.exit(1 if failures else 0)
