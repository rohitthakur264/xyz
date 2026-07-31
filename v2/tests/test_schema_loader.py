import os
import sys

# Setup python path to include v2 root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.schema_loader import SchemaLoader
from database.relationship_graph import RelationshipGraph
from database.schema_hash import SchemaHasher
from rag.embedding_builder import EmbeddingBuilder
from rag.vector_store import VectorStore
import json

def test_sprint_2():
    print("Testing Schema Loader...")
    loader = SchemaLoader()
    schema = loader.load_schema()
    
    # Verify no 'old*' columns
    for t, info in schema.items():
        for c in info["columns"]:
            if c["column_name"].lower().startswith("old"):
                raise AssertionError(f"Found 'old' column {c['column_name']} in table {t}")
    print(f"Schema loaded successfully with {len(schema)} tables. Sanitization passed.")
    
    print("Testing Relationship Graph...")
    graph = RelationshipGraph(schema)
    path = graph.find_shortest_path("fhir_patient_mst", "fhir_bill_mst")
    print(f"Path between fhir_patient_mst and fhir_bill_mst: {path}")
    
    # Inject relationships back into schema
    graph.populate_schema_relationships()
    
    print("Testing Schema Hasher...")
    hasher = SchemaHasher()
    current_hash = hasher.compute_hash(schema)
    print(f"Computed Schema Hash: {current_hash}")
    
    print("Testing Embedding Builder...")
    # Just build text for the first table
    t_name = list(schema.keys())[0]
    embed_text = EmbeddingBuilder.build_table_embedding_text(schema[t_name])
    metadata = EmbeddingBuilder.build_table_metadata(schema[t_name])
    print(f"Sample Embedding Text (len={len(embed_text)}):\n{embed_text}")
    print(f"Sample Metadata: {metadata}")
    
    print("Testing Vector Store Initialization...")
    store = VectorStore(persist_dir="tests/chroma_test")
    # Load examples from json using relative path from tests directory
    examples_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sql_examples.json")
    with open(examples_path, "r") as f:
        examples = json.load(f)
    print(f"Loaded {len(examples)} examples.")
    
    print("ALL TESTS PASSED.")

if __name__ == "__main__":
    test_sprint_2()
