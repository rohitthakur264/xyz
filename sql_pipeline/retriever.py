import os
import json
import chromadb
from chromadb.utils import embedding_functions

CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_data")
SCHEMA_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "schema_intel", "schema_cache.json")

def retrieve_tables(question, k=5):
    """
    Search ChromaDB for top-K relevant tables for the given question.
    Returns a dictionary of the full schema (columns + fks) for those tables,
    by reading from the cached schema.
    """
    if not os.path.exists(SCHEMA_CACHE_PATH):
        print("Schema cache not found. Run extractor.py first.")
        return {}

    with open(SCHEMA_CACHE_PATH, 'r') as f:
        schema_cache = json.load(f)

    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer('all-MiniLM-L6-v2')
    try:
        collection = client.get_collection(name="schema_collection")
    except Exception as e:
        print("Could not load Chroma collection. Did you run Phase 1 embedder?", e)
        return {}

    query_embeddings = embedder.encode([question]).tolist()
    results = collection.query(
        query_embeddings=query_embeddings,
        n_results=k
    )

    retrieved_schema = {}
    if results and results.get('ids') and results['ids'][0]:
        base_tables = [t.replace("schema_", "") if t.startswith("schema_") else t for t in results['ids'][0]]
        tables_to_include = set(base_tables)
        # Always include core patient table
        tables_to_include.add("fhir_patient_mst")
        
        # Keyword domain table expansion — maps keywords to VERIFIED real DB tables
        # Confirmed from live DB probing against patient 180267:
        #   - fhir_order_mst uses ordpatientid/ordvisitid (NOT patientid/visitid)
        #   - fhir_drug_sale_mst.visitid does NOT match fhir_visit_mst.id (different system)
        #   - fhir_tprbp_dtl has NO patientid — must join via visit_id
        #   - fhir_bill_mst has registration_no (direct lookup, no join needed)
        #   - fhir_drug_mst: catalog of 36879 drugs, linked via order_dtl.service_id
        q_lower = question.lower()
        keyword_table_map = {
            # PRESCRIPTIONS / DRUGS: order system is the working path
            # fhir_order_mst (ordpatientid) -> fhir_order_dtl -> fhir_drug_mst
            "prescription": ["fhir_order_mst", "fhir_order_dtl", "fhir_drug_mst", "fhir_prescription_dtl"],
            "medicine": ["fhir_order_mst", "fhir_order_dtl", "fhir_drug_mst"],
            "drug": ["fhir_order_mst", "fhir_order_dtl", "fhir_drug_mst", "fhir_drug_sale_mst"],
            "dispens": ["fhir_drug_sale_mst", "fhir_drug_sale_dtl", "fhir_drug_mst"],
            # VISIT
            "visit": ["fhir_visit_mst"],
            # BILLING
            "bill": ["fhir_bill_mst"],
            "billing": ["fhir_bill_mst"],
            # VITALS
            "vital": ["fhir_patient_vitals", "fhir_tprbp_dtl"],
            # ALLERGY
            "allergy": ["fhir_patient_allergy"],
            # SURGERY/OT
            "surgery": ["fhir_ot_scheduling_mst", "fhir_ot_schedule_mst"],
            "operation": ["fhir_ot_scheduling_mst", "fhir_ot_schedule_mst"],
            # LAB
            "lab": ["fhir_lab_test_mst", "fhir_lab_test_result", "fhir_lab_test_param"],
            "test": ["fhir_lab_test_mst", "fhir_lab_test_result", "fhir_lab_test_param"],
            # ORDERS
            "order": ["fhir_order_mst", "fhir_order_dtl"],
            # DIAGNOSIS
            "diagnos": ["fhir_patient_diagnosis"],
        }
        for kw, tbls in keyword_table_map.items():
            if kw in q_lower:
                for t in tbls:
                    if t in schema_cache:
                        tables_to_include.add(t)
        
        # Expand context by pulling in any table referenced by a foreign key
        for table_name in list(tables_to_include):
            if table_name in schema_cache:
                for fk in schema_cache[table_name]['fks']:
                    if fk['referenced_table']:
                        tables_to_include.add(fk['referenced_table'])
                    
        for table_name in tables_to_include:
            if table_name in schema_cache:
                retrieved_schema[table_name] = schema_cache[table_name]
                
    return retrieved_schema
