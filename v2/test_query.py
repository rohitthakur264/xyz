import sys
import os
import json
import asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm.llm_client import LLMClient
from sql_pipeline.intent_detector import IntentDetector
from sql_pipeline.query_planner import QueryPlanner
from sql_pipeline.sql_generator import SQLGenerator
from sql_pipeline.sql_corrector import SQLCorrector
from sql_pipeline.sql_validator import SQLValidator
from database.schema_loader import SchemaLoader
from database.schema_anchors import merge_extra_relationships
from database.db_manager import DatabaseManager
from database.relationship_graph import RelationshipGraph
from rag.vector_store import VectorStore
from rag.schema_retriever import SchemaRetriever
from rag.example_retriever import ExampleRetriever
from memory.session_manager import SessionState

async def test():
    print("Initializing...")
    llm = LLMClient()
    loader = SchemaLoader()
    schema = loader.load_schema()
    merge_extra_relationships(schema)
    
    vs = VectorStore()
    schema_retriever = SchemaRetriever(vs, schema)
    example_retriever = ExampleRetriever(vs)
    graph = RelationshipGraph(schema)
    
    intent_detector = IntentDetector(llm)
    query_planner = QueryPlanner(schema_retriever, example_retriever, graph)
    sql_gen = SQLGenerator(llm, schema)
    sql_corrector = SQLCorrector(llm, schema)
    db = DatabaseManager()
    sql_validator = SQLValidator(schema, db)
    
    question = "registration no 166637"
    session = SessionState("test_session")
    
    intents = intent_detector.detect_intent(question)
    print(f"Intents: {intents}")
    
    intent = intents[0]
    plan = query_planner.plan_query(question, intent, session)
    print(f"Plan tables: {plan['tables']}")
    
    sql = sql_gen.generate(question, plan)
    print(f"Generated SQL: {sql}")
    
    errors = sql_validator.validate_query(sql, plan["tables"])
    if errors:
        print(f"Validation errors: {errors}")
        sql = sql_corrector.correct(sql, errors, question, plan)
        print(f"Corrected SQL: {sql}")
        errors = sql_validator.validate_query(sql, plan["tables"])
        if errors:
            print(f"Validation errors after correction: {errors}")
    
    if not errors:
        df = db.execute_query(sql)
        if df is not None:
            print(f"Query returned {len(df)} rows")
            print(df)
        else:
            print("Query failed execution")

if __name__ == "__main__":
    asyncio.run(test())
