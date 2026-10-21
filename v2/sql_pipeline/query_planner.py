import os
import json
from rag.schema_retriever import SchemaRetriever
from rag.example_retriever import ExampleRetriever
from database.relationship_graph import RelationshipGraph
from database.schema_anchors import find_anchor_tables, load_table_mappings
from memory.session_manager import SessionState
from config.logging import get_logger

logger = get_logger(__name__)

class QueryPlanner:
    """Plans the SQL generation by identifying necessary schema context and examples."""

    def __init__(self, schema_retriever: SchemaRetriever, example_retriever: ExampleRetriever, graph: RelationshipGraph):
        self.schema_retriever = schema_retriever
        self.example_retriever = example_retriever
        self.graph = graph
        # Master anchor tables are derived from the live schema, then enriched with explicit mappings.
        self.anchors = find_anchor_tables(self.graph.schema)
        try:
            mapped_anchors = load_table_mappings(self.graph.schema)
            # Ensure mapped anchors are simple strings (some mappings in JSON are dicts for dropdowns)
            for k, v in mapped_anchors.items():
                if isinstance(v, dict) and "table" in v:
                    self.anchors[k] = v["table"]
                elif isinstance(v, str):
                    self.anchors[k] = v
        except Exception as e:
            logger.error(f"Failed to load table mappings into QueryPlanner: {e}")

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
                    
        # 4. Context injection (if patient/visit context exists, include their master tables)
        patient_tbl = self.anchors.get("patient")
        visit_tbl = self.anchors.get("visit")

        if session.patient and patient_tbl and patient_tbl not in retrieved_tables:
            retrieved_tables.append(patient_tbl)

        if session.visit and visit_tbl and visit_tbl not in retrieved_tables:
            retrieved_tables.append(visit_tbl)
            
        # Intent-based forced tables to ensure verified schema coverage and prevent hallucination
        INTENT_ANCHOR_MAP = {
            "ALLERGY": ["allergy_nurse", "allergy_medicine", "allergy_food", "allergy_general", "visit", "patient"],
            "PRESCRIPTION": ["prescription_master", "prescription_detail", "drug", "frequency", "visit", "patient"],
            "VITALS": ["vitals", "visit", "patient"],
            "BILLING": ["billing", "visit", "patient"],
            "VISIT": ["visit", "ward", "room", "bed", "doctor", "department", "patient"],
            "SURGERY": ["operation_scheduling", "operation_detail", "service", "visit", "patient"],
            "LAB": ["lab_result", "visit", "patient"],
            "RADIOLOGY": ["radiology_result", "radiology_services", "radiology_template", "visit", "patient"],
            "DISCHARGE_SUMMARY": ["discharge_summary", "discharge_type", "visit", "patient"],
            "PATIENT_SEARCH": ["patient", "gender", "nationality"],
        }

        if intent in INTENT_ANCHOR_MAP:
            for t_key in INTENT_ANCHOR_MAP[intent]:
                db_tbl = self.anchors.get(t_key)
                if not db_tbl and t_key == "billing":
                    db_tbl = "fhir_bill_mst"
                if db_tbl and db_tbl not in retrieved_tables:
                    retrieved_tables.append(db_tbl)

        # 5. Use Graph to bridge disconnected tables and collect join hints
        final_tables = set(retrieved_tables)

        joins = []
        
        # Connect every table to the active patient table if possible
        if patient_tbl:
            for t in list(final_tables):
                if t != patient_tbl:
                    path = self.graph.find_shortest_path(t, patient_tbl)
                    if path:
                        for p_table in path:
                            final_tables.add(p_table)
                        for j in self.graph.get_join_conditions(path):
                            if j not in joins:
                                joins.append(j)

        # Also connect every table to the visit table if it is present
        if visit_tbl and session.visit:
            for t in list(final_tables):
                if t != visit_tbl:
                    path = self.graph.find_shortest_path(t, visit_tbl)
                    if path:
                        for p_table in path:
                            final_tables.add(p_table)
                        for j in self.graph.get_join_conditions(path):
                            if j not in joins:
                                joins.append(j)

        # Force-bridge visit table for intents that include it (e.g., VITALS, LAB, PRESCRIPTION)
        # This ensures visit_no can always be fetched, even when no active visit is in the session.
        if visit_tbl and visit_tbl in final_tables and not session.visit:
            for t in list(final_tables):
                if t != visit_tbl:
                    path = self.graph.find_shortest_path(t, visit_tbl)
                    if path:
                        for p_table in path:
                            final_tables.add(p_table)
                        for j in self.graph.get_join_conditions(path):
                            if j not in joins:
                                joins.append(j)

        plan = {
            "intent": intent,
            "tables": list(final_tables),
            "joins": joins,
            "examples": retrieved_examples,
            "session_context": session.get_context_summary()
        }
        logger.info(f"Query Plan finalized. Tables: {plan['tables']}")
        return plan
