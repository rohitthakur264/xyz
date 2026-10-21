"""
Smoke test for the intent_detector.py fix.

Verifies:
  1. Genuine data questions that happen to contain "what is" / "how to" etc.
     are NOT short-circuited to CONVERSATIONAL anymore (the bug).
  2. Real definitional / general-knowledge questions still correctly bypass
     to CONVERSATIONAL (no regression).
  3. The existing fast keyword-map path (<=3 words) still works.

No live LLM or DB needed — a FakeLLM stub is used for the few cases that
fall through to the "ask the model" path.

Run with:
    cd v2
    python -m pytest tests/smoke/test_intent_detector_smoke.py -v
or directly:
    python tests/smoke/test_intent_detector_smoke.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# settings.py raises if DB_NAME isn't set — provide a dummy value for the smoke test.
os.environ.setdefault("DB_NAME", "smoke_test_db")

from sql_pipeline.intent_detector import IntentDetector  # noqa: E402


class FakeLLM:
    """Stub LLM client. Returns a canned intent so we can test the code path
    that fires ONLY when the fast-path heuristics don't already resolve the
    question (i.e. proves the question correctly reached the LLM stage)."""

    def __init__(self, canned_response="PATIENT_SEARCH"):
        self.canned_response = canned_response
        self.calls = []

    def generate(self, prompt, model=None, temperature=0.0):
        self.calls.append(prompt)
        return self.canned_response


# ---------------------------------------------------------------------------
# Case 1: previously-broken data questions -> must NOT be CONVERSATIONAL,
# and must actually reach the LLM (proving the fast-path bypass is gone).
# ---------------------------------------------------------------------------
BUG_REGRESSION_CASES = [
    "what is the phone number of patient rahul?",
    "what is the BP of patient 123?",
    "what is the blood pressure trend for this patient",
    "what is the current temperature of patient 456",
    "what is the billing amount for this visit",
    "how to check the vitals of patient rahul",
]

# ---------------------------------------------------------------------------
# Case 2: genuine definitional / general-knowledge questions -> must STILL
# be fast-pathed to CONVERSATIONAL (no regression).
# ---------------------------------------------------------------------------
CONVERSATIONAL_CASES = [
    "what is crocin used for?",
    "what is a stroke",
    "how to take metformin",
    "explain the vitals report",
    "what is the use of paracetamol",
    "post care instructions",
    "precautions after surgery",
]

# ---------------------------------------------------------------------------
# Case 3: fast keyword-map path (<=3 words) must still work untouched.
# ---------------------------------------------------------------------------
KEYWORD_CASES = [
    ("vitals", "VITALS"),
    ("billing", "BILLING"),
    ("allergies", "ALLERGY"),
    ("lab report", "LAB"),
]


def run():
    failures = []

    # --- Case 1 ---
    fake_llm = FakeLLM(canned_response="PATIENT_SEARCH")
    detector = IntentDetector(fake_llm)
    for q in BUG_REGRESSION_CASES:
        calls_before = len(fake_llm.calls)
        result = detector.detect_intent(q)
        reached_llm = len(fake_llm.calls) > calls_before
        if result == ["CONVERSATIONAL"]:
            failures.append(f"[REGRESSION] '{q}' was wrongly fast-pathed to CONVERSATIONAL")
        elif not reached_llm:
            failures.append(f"[UNEXPECTED] '{q}' resolved to {result} without hitting the LLM "
                             f"(check fast keyword-map didn't accidentally match)")
        else:
            print(f"OK  '{q}' -> {result} (reached LLM, not CONVERSATIONAL)")

    # --- Case 2 ---
    fake_llm2 = FakeLLM(canned_response="GENERAL")  # if this fires, it's wrong for these cases
    detector2 = IntentDetector(fake_llm2)
    for q in CONVERSATIONAL_CASES:
        result = detector2.detect_intent(q)
        if result != ["CONVERSATIONAL"]:
            failures.append(f"[REGRESSION] '{q}' should fast-path to CONVERSATIONAL but got {result}")
        else:
            print(f"OK  '{q}' -> {result}")

    # --- Case 3 ---
    fake_llm3 = FakeLLM()
    detector3 = IntentDetector(fake_llm3)
    for q, expected in KEYWORD_CASES:
        result = detector3.detect_intent(q)
        if result != [expected]:
            failures.append(f"[REGRESSION] '{q}' expected {[expected]}, got {result}")
        else:
            print(f"OK  '{q}' -> {result}")

    print()
    total = len(BUG_REGRESSION_CASES) + len(CONVERSATIONAL_CASES) + len(KEYWORD_CASES)
    if failures:
        print(f"FAILED: {len(failures)} of {total} case(s) failed")
        for f in failures:
            print("  -", f)
    else:
        print(f"PASSED: all {total} cases OK")
    return failures


def test_intent_detector_smoke():
    """pytest entry point."""
    failures = run()
    assert not failures, f"{len(failures)} smoke test case(s) failed: {failures}"


if __name__ == "__main__":
    failures = run()
    sys.exit(1 if failures else 0)
