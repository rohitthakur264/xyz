import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.llm_client import LLMClient
from sql_pipeline.intent_detector import IntentDetector
from database.schema_loader import SchemaLoader
from database.relationship_graph import RelationshipGraph
from rag.vector_store import VectorStore
from rag.schema_retriever import SchemaRetriever
from rag.example_retriever import ExampleRetriever
from sql_pipeline.query_planner import QueryPlanner
from services.chat_orchestrator import ChatOrchestrator
from memory.session_manager import SessionManager
from memory.patient_context import PatientContext

def test_sprint_3():
    print("Initializing components...")
    
    # Mock LLM response to avoid network call in tests
    class MockLLMClient:
        def generate(self, prompt, model=None, temperature=None):
            return "Mocked Answer"
            
    llm = MockLLMClient()
    intent_detector = IntentDetector(llm)
    
    loader = SchemaLoader()
    schema = loader.load_schema()
    graph = RelationshipGraph(schema)
    
    store = VectorStore(persist_dir="tests/chroma_test")
    schema_retriever = SchemaRetriever(store)
    example_retriever = ExampleRetriever(store)
    
    planner = QueryPlanner(schema_retriever, example_retriever, graph)
    orchestrator = ChatOrchestrator(
        intent_detector=intent_detector,
        query_planner=planner,
        sql_corrector=None,
        answer_generator=None
    )
    
    print("Testing Session State injection...")
    session = SessionManager.get_or_create_session("sess_123", "doc_001")
    session.patient = PatientContext(patient_id="180267", name="MARAD")
    
    print("Executing query...")
    res = orchestrator.handle_message("sess_123", "doc_001", "Show me the patient's billing details")
    
    print(f"Result: {res}")
    
    if "BILLING" != res["intent"]:
        raise AssertionError("Intent was not BILLING")
        
    if "fhir_patient_mst" not in res["tables"]:
        raise AssertionError("Patient table not injected by context")
        
    print("ALL TESTS PASSED.")

if __name__ == "__main__":
    test_sprint_3()
