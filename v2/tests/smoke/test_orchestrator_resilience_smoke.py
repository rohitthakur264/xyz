"""
Smoke test for the "demo must not crash" resilience fix in chat_orchestrator.py.

Verifies:
  1. handle_message() NEVER raises — even if the real pipeline
     (_handle_message_impl) throws (simulating: LLM rate-limit TimeoutError,
     a DB hiccup, or any unexpected exception). It must always return a valid
     dict with a friendly "busy, try again" answer instead.
  2. Identical repeated questions (same session_id) are served from the
     in-memory cache on the 2nd+ call — the expensive pipeline is NOT
     re-invoked. This is the main lever for reducing how often we hit the
     LLM rate limit at all during a demo (presenters repeat questions a lot).
  3. Error/degraded responses are never cached (so a transient rate-limit
     failure doesn't get "stuck" and returned forever afterwards).
  4. A DIFFERENT question (or different session) is a cache miss and goes
     through the real pipeline.

No live LLM, MySQL, ChromaDB, or Ollama needed — the real pipeline
(_handle_message_impl) is monkey-patched with a lightweight fake so we can
control exactly what it does per call.

Run with:
    cd v2
    python -m pytest tests/smoke/test_orchestrator_resilience_smoke.py -v
or directly:
    python tests/smoke/test_orchestrator_resilience_smoke.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DB_NAME", "smoke_test_db")

# This test exercises only the resilience wrapper (caching + top-level
# try/except) around _handle_message_impl, which we monkey-patch below —
# the real pipeline code never runs. So heavy optional dependencies pulled
# in transitively by chat_orchestrator's imports (chromadb, sentence
# embeddings, etc.) don't need to be installed; stub them out if missing.
import types  # noqa: E402
import importlib.util  # noqa: E402

for _mod_name in ("chromadb", "networkx"):
    if importlib.util.find_spec(_mod_name) is None:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)

if importlib.util.find_spec("sentence_transformers") is None:
    _st_stub = types.ModuleType("sentence_transformers")
    _st_stub.SentenceTransformer = object  # never instantiated in this test
    sys.modules["sentence_transformers"] = _st_stub

from services.chat_orchestrator import ChatOrchestrator  # noqa: E402


def _make_orchestrator():
    # ChatOrchestrator.__init__ just stores references, no DB/LLM calls happen
    # at construction time — safe to pass None/dummy placeholders here since
    # we monkey-patch _handle_message_impl directly for these tests anyway.
    return ChatOrchestrator(
        intent_detector=None,
        query_planner=None,
        sql_corrector=None,
        answer_generator=None,
        patient_resolver=None,
    )


def run():
    failures = []

    # ---------------------------------------------------------------
    # Case 1: pipeline raises -> handle_message must NOT raise, must
    # return a friendly fallback dict instead of crashing the request.
    # ---------------------------------------------------------------
    orch = _make_orchestrator()

    def _boom(session_id, doctor_id, question):
        raise TimeoutError("AI service is currently experiencing heavy load (rate limited).")

    orch._handle_message_impl = _boom

    try:
        result = orch.handle_message("session_A", "doc_1", "vitals detail")
        required_keys = {"answer", "sql", "intent", "tables"}
        if not required_keys.issubset(result.keys()):
            failures.append(f"[SCHEMA] fallback response missing keys: {required_keys - result.keys()}")
        elif not result.get("answer"):
            failures.append("[SCHEMA] fallback response has empty answer")
        else:
            print(f"OK  pipeline exception -> handled gracefully: {result['answer'][:60]}...")
    except Exception as e:
        failures.append(f"[CRASH] handle_message raised instead of catching: {e}")

    # ---------------------------------------------------------------
    # Case 2: that failed call must NOT have been cached (no "stuck"
    # error responses) — asking again should call the pipeline again.
    # ---------------------------------------------------------------
    call_count = {"n": 0}

    def _still_failing(session_id, doctor_id, question):
        call_count["n"] += 1
        raise TimeoutError("still rate limited")

    orch._handle_message_impl = _still_failing
    orch.handle_message("session_A", "doc_1", "vitals detail")
    if call_count["n"] != 1:
        failures.append(f"[REGRESSION] expected pipeline to be called again after a prior failure "
                         f"(error responses must not be cached), got {call_count['n']} calls")
    else:
        print("OK  failed responses are not cached (pipeline re-invoked on retry)")

    # ---------------------------------------------------------------
    # Case 3: successful response IS cached — repeated identical
    # question in the same session must not re-invoke the pipeline.
    # ---------------------------------------------------------------
    orch2 = _make_orchestrator()
    call_count2 = {"n": 0}

    def _success(session_id, doctor_id, question):
        call_count2["n"] += 1
        return {
            "answer": f"Here are the vitals (call #{call_count2['n']}).",
            "sql": "SELECT ...",
            "intent": "VITALS",
            "tables": ["fhir_vitals"],
            "patient": {"name": "Test Patient", "reg_no": "REG-1", "id": "P1"},
            "raw_data": [{"Systolic BP": 120}],
        }

    orch2._handle_message_impl = _success

    r1 = orch2.handle_message("session_B", "doc_1", "vitals detail")
    r2 = orch2.handle_message("session_B", "doc_1", "vitals detail")  # same question again
    r3 = orch2.handle_message("session_B", "doc_1", "  Vitals Detail  ")  # same, different case/whitespace

    if call_count2["n"] != 1:
        failures.append(f"[REGRESSION] expected pipeline to be called exactly once for repeated "
                         f"identical questions (cache should serve 2nd/3rd call), got {call_count2['n']} calls")
    elif r1["answer"] != r2["answer"] or r1["answer"] != r3["answer"]:
        failures.append("[REGRESSION] cached response content differs between repeated calls")
    else:
        print(f"OK  repeated question served from cache (pipeline called {call_count2['n']}x for 3 requests)")

    # ---------------------------------------------------------------
    # Case 4: a genuinely different question -> cache miss, pipeline runs again.
    # ---------------------------------------------------------------
    r4 = orch2.handle_message("session_B", "doc_1", "billing detail")
    if call_count2["n"] != 2:
        failures.append(f"[REGRESSION] a different question should be a cache miss and invoke the "
                         f"pipeline again, got {call_count2['n']} total calls (expected 2)")
    else:
        print("OK  different question is a cache miss, pipeline invoked")

    print()
    if failures:
        print(f"FAILED: {len(failures)} issue(s) found")
        for f in failures:
            print("  -", f)
    else:
        print("PASSED: all 4 cases OK")
    return failures


def test_orchestrator_resilience_smoke():
    """pytest entry point."""
    failures = run()
    assert not failures, f"{len(failures)} smoke test case(s) failed: {failures}"


if __name__ == "__main__":
    failures = run()
    sys.exit(1 if failures else 0)
