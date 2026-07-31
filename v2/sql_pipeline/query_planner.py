from rag.schema_retriever import SchemaRetriever
from rag.example_retriever import ExampleRetriever
from database.relationship_graph import RelationshipGraph
from memory.session_manager import SessionState
from config.logging import get_logger

logger = get_logger(__name__)

class QueryPlanner:
    """Plans the SQL generation by identifying necessary schema context and examples."""
    
    def __init__(self, schema_retriever: SchemaRetriever, example_retriever: ExampleRetriever, graph: RelationshipGraph):
        self.schema_retriever = schema_retriever
        self.example_retriever = example_retriever
        self.graph = graph

    def plan_query(self, question: str, intent: str, session: SessionState) -> dict:
        """
        Builds a QueryPlan containing the required tables and examples.
        """
        logger.info(f"Planning query for intent: {intent}")
        
        # 1. Retrieve initial tables based on semantic similarity
        retrieved_tables = self.schema_retriever.retrieve_tables(question, intent)
        
        # 2. Retrieve examples
        retrieved_examples = self.example_retriever.retrieve_examples(question, intent)
        
        # 3. Add tables from examples to ensure coverage
        for ex in retrieved_examples:
            for t in ex["tables"]:
                if t not in retrieved_tables:
                    retrieved_tables.append(t)
                    
        # 4. Context injection (if patient context exists, we almost always need fhir_patient_mst)
        if session.patient and "fhir_patient_mst" not in retrieved_tables:
            retrieved_tables.append("fhir_patient_mst")
            
        if session.visit and "fhir_visit_mst" not in retrieved_tables:
            retrieved_tables.append("fhir_visit_mst")
            
        # 5. Use Graph to bridge disconnected tables
        final_tables = set(retrieved_tables)
        if len(retrieved_tables) >= 2:
            # Simple heuristic: try to connect the first table to the rest
            base_table = retrieved_tables[0]
            for target_table in retrieved_tables[1:]:
                path = self.graph.find_shortest_path(base_table, target_table)
                if path:
                    for t in path:
                        final_tables.add(t)
                        
        plan = {
            "intent": intent,
            "tables": list(final_tables),
            "examples": retrieved_examples,
            "session_context": session.get_context_summary()
        }
        logger.info(f"Query Plan finalized. Tables: {plan['tables']}")
        return plan
