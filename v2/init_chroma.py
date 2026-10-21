import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.schema_loader import SchemaLoader
from database.schema_anchors import merge_extra_relationships
from rag.embedding_builder import EmbeddingBuilder
from rag.vector_store import VectorStore
from config.logging import get_logger

logger = get_logger(__name__)

def init():
    print("Loading schema...")
    loader = SchemaLoader()
    schema = loader.load_schema()
    
    # Merge extra relationships
    merge_extra_relationships(schema)
    
    table_texts = {}
    metadata_dicts = {}
    
    print(f"Building embeddings for {len(schema)} tables...")
    for t_name, table_info in schema.items():
        text = EmbeddingBuilder.build_table_embedding_text(table_info)
        meta = EmbeddingBuilder.build_table_metadata(table_info)
        table_texts[t_name] = text
        metadata_dicts[t_name] = meta
        
    print("Updating Vector Store...")
    vs = VectorStore()
    vs.update_schema(table_texts, metadata_dicts)
    print("Database schema successfully embedded into ChromaDB!")

if __name__ == "__main__":
    init()
