from rag.vector_store import VectorStore
from config.settings import SCHEMA_RETRIEVAL_K
from config.logging import get_logger

logger = get_logger(__name__)

class SchemaRetriever:
    """Retrieves relevant table schemas based on the question and intent."""
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        
    def retrieve_tables(self, question: str, intent: str = "GENERAL", k: int = SCHEMA_RETRIEVAL_K) -> list:
        """
        Retrieves the top k table names and their descriptions.
        """
        logger.info(f"Retrieving schema context for: '{question}' (Intent: {intent})")
        
        # Simple metadata filtering by module could be done here based on intent
        # For now, we retrieve purely semantically from the schema collection
        results = self.vector_store.schema_collection.query(
            query_embeddings=self.vector_store._get_embeddings([question]),
            n_results=k
        )
        
        tables = []
        if results:
            metadatas_list = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
            ids_list = results.get("ids", [[]])[0] if results.get("ids") else []
            
            for idx, metadata in enumerate(metadatas_list):
                tbl = None
                if metadata:
                    tbl = metadata.get("table") or metadata.get("table_name")
                if not tbl and idx < len(ids_list):
                    raw_id = ids_list[idx]
                    tbl = raw_id.replace("schema_", "") if raw_id.startswith("schema_") else raw_id
        # Keyword domain table expansion
        q_lower = question.lower()
        keyword_table_map = {
            "visit": ["fhir_visit_mst"],
            "encounter": ["fhir_visit_mst", "fhir_encounter"],
            "bill": ["fhir_bill_mst"],
            "billing": ["fhir_bill_mst"],
            "prescription": ["fhir_order_mst", "fhir_order_dtl", "fhir_drug_mst", "fhir_prescription_dtl"],
            "medicine": ["fhir_order_mst", "fhir_order_dtl", "fhir_drug_mst"],
            "drug": ["fhir_order_mst", "fhir_order_dtl", "fhir_drug_mst", "fhir_drug_sale_mst"],
            "vital": ["fhir_patient_vitals", "fhir_tprbp_dtl"],
            "allergy": ["fhir_patient_allergy"],
            "lab": ["fhir_lab_test_mst", "fhir_lab_test_result", "fhir_lab_test_param"],
            "test": ["fhir_lab_test_mst", "fhir_lab_test_result", "fhir_lab_test_param"],
            "order": ["fhir_order_mst", "fhir_order_dtl"],
            "diagnos": ["fhir_patient_diagnosis"],
        }
        for kw, tbls in keyword_table_map.items():
            if kw in q_lower:
                for t in tbls:
                    if t not in tables:
                        tables.append(t)

        logger.info(f"Retrieved {len(tables)} tables: {tables}")
        return tables
