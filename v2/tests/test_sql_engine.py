import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sql_pipeline.sql_validator import SQLValidator
from sql_pipeline.sql_corrector import SQLCorrector
from sql_pipeline.sql_generator import SQLGenerator
from database.query_executor import QueryExecutor

def test_sprint_4():
    print("Testing SQL Validator...")
    # Mock schema cache
    schema_cache = {
        "fhir_patient_mst": {"columns": [{"column_name": "id", "data_type": "int"}]},
        "fhir_visit_mst": {"columns": [{"column_name": "id", "data_type": "int"}]}
    }
    validator = SQLValidator(schema_cache)
    
    # Test 1: Valid SQL
    errs = validator.validate("SELECT * FROM fhir_patient_mst", allowed_tables=["fhir_patient_mst"])
    assert len(errs) == 0, "Valid SQL should pass"
    
    # Test 2: Dangerous SQL
    errs = validator.validate("DELETE FROM fhir_patient_mst", allowed_tables=["fhir_patient_mst"])
    assert len(errs) > 0 and any("DANGEROUS" in e for e in errs), "Should catch DELETE"
    
    # Test 3: Unallowed Table
    errs = validator.validate("SELECT * FROM fhir_bill_mst", allowed_tables=["fhir_patient_mst"])
    assert len(errs) > 0 and any("Hallucinated" in e for e in errs), "Should catch hallucinated table"
    
    print("Testing SQL Generator cleanup...")
    class MockOllama:
        def generate(self, prompt, **kwargs):
            return "```sql\nSELECT * FROM t;\n```"
            
    generator = SQLGenerator(MockOllama(), schema_cache)
    clean_sql = generator.generate("dummy", {"tables": [], "examples": [], "session_context": ""})
    assert clean_sql == "SELECT * FROM t", f"SQL cleaner failed: {clean_sql}"
    
    print("Testing SQL Corrector / Execution Loop (Mocked)...")
    class MockExecutor:
        def __init__(self):
            self.attempts = 0
        def execute(self, sql):
            self.attempts += 1
            if self.attempts < 3:
                return {"success": False, "error": "Unknown column 'foo'"}
            return {"success": True, "rows": [{"id": 1}], "error": None}
            
    class RetryMockOllama:
        def generate(self, prompt, **kwargs):
            return "SELECT * FROM fhir_patient_mst"
            
    corrector = SQLCorrector(
        SQLGenerator(RetryMockOllama(), schema_cache),
        validator,
        MockExecutor()
    )
    
    res = corrector.run_pipeline("test", {"tables": ["fhir_patient_mst"], "examples": [], "session_context": ""})
    assert res["result"]["success"] is True, "Corrector should eventually succeed"
    assert res["retries"] == 2, "Corrector should have taken 2 retries (3rd attempt succeeded)"
    
    print("ALL SPRINT 4 TESTS PASSED.")

if __name__ == "__main__":
    test_sprint_4()
