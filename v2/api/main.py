import sys
import os

# Add v2 root at start of python path so v2 config imports take priority
v2_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if v2_dir not in sys.path:
    sys.path.insert(0, v2_dir)

from fastapi import FastAPI
from api.health import run_health_checks
from api import routes
from config.logging import get_logger

from database.schema_loader import SchemaLoader
from database.schema_anchors import merge_extra_relationships, load_table_mappings
from database.relationship_graph import RelationshipGraph
from database.query_executor import QueryExecutor
from rag.vector_store import VectorStore
from rag.schema_retriever import SchemaRetriever
from rag.example_retriever import ExampleRetriever
from rag.example_learner import ExampleLearner
from llm.llm_client import LLMClient
from llm.answer_generator import AnswerGenerator
from sql_pipeline.intent_detector import IntentDetector
from sql_pipeline.query_planner import QueryPlanner
from sql_pipeline.sql_generator import SQLGenerator
from sql_pipeline.sql_validator import SQLValidator
from sql_pipeline.sql_corrector import SQLCorrector
from services.patient_resolver import PatientResolver
from services.chat_orchestrator import ChatOrchestrator
from services.document_generator import validate_report_schema

logger = get_logger(__name__)

# Run health checks before starting the app
try:
    run_health_checks()
except Exception as e:
    logger.critical(f"Failed to start Application: {e}")
    sys.exit(1)

# Global Initialization
logger.info("Initializing global components...")

# 1. DB / Schema
loader = SchemaLoader()
full_schema = loader.load_schema()
# Enrich with relationships the DB does not declare as FKs (see extra_relationships.json)
merge_extra_relationships(full_schema)

# Load frozen config anchors (fails fast if missing or critical mismatch)
anchors = load_table_mappings(full_schema)

# Validate report config against schema (fails fast if mismatch)
validate_report_schema(full_schema, anchors)

graph = RelationshipGraph(full_schema)
executor = QueryExecutor()
patient_resolver = PatientResolver(executor, anchors)

# 2. RAG
store = VectorStore()
# Learn few-shot examples dynamically from successful audit-log executions.
# Data-driven, no hardcoded examples: only real queries that returned rows are seeded.
# try:
#     learned = ExampleLearner(store, full_schema).learn()
#     logger.info(f"ExampleLearner seeded {learned} examples into the collection.")
# except Exception as e:
#     logger.warning(f"ExampleLearner failed (continuing without examples): {e}")

schema_retriever = SchemaRetriever(store)
example_retriever = ExampleRetriever(store)

# 3. LLM / Planning
llm = LLMClient()
intent_detector = IntentDetector(llm)
query_planner = QueryPlanner(schema_retriever, example_retriever, graph)
answer_generator = AnswerGenerator(llm)

# 4. SQL Engine
validator = SQLValidator(full_schema, graph)
generator = SQLGenerator(llm, full_schema)
sql_corrector = SQLCorrector(generator, validator, executor)

# 5. Orchestrator
orchestrator = ChatOrchestrator(intent_detector, query_planner, sql_corrector, answer_generator, patient_resolver)
routes.orchestrator = orchestrator

app = FastAPI(
    title="Hospital AI Assistant (v2)",
    description="Production-grade EMR AI Assistant API"
)

app.include_router(routes.router)

@app.get("/")
def root_endpoint():
    return {
        "message": "Hospital AI Assistant API (v2) is running",
        "docs": "http://127.0.0.1:8001/docs",
        "health": "http://127.0.0.1:8001/health"
    }

@app.get("/health")
def health_endpoint():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
