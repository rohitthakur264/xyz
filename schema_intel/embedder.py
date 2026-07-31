import os
import json
import chromadb
from chromadb.utils import embedding_functions

INPUT_FILE = os.path.join(os.path.dirname(__file__), "table_descriptions.json")
SCHEMA_CACHE_FILE = os.path.join(os.path.dirname(__file__), "schema_cache.json")
CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_data")

def embed_descriptions():
    """
    Reads human-reviewed table descriptions from table_descriptions.json
    and embeds them into ChromaDB.
    """
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found. Run generator.py and review it first.")
        return

    with open(INPUT_FILE, 'r') as f:
        descriptions = json.load(f)

    if not descriptions:
        print("No descriptions to embed.")
        return

    print("Connecting to ChromaDB...")
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer('all-MiniLM-L6-v2')

    collection = client.get_or_create_collection(
        name="schema_collection",
        metadata={"description": "Database Schema and Table metadata"}
    )

    ids = []
    documents = []
    metadatas = []

    with open(SCHEMA_CACHE_FILE, 'r') as f:
        schema_cache = json.load(f)

    for table_name, desc in descriptions.items():
        # Append column names to the description to help vector search match exact terms
        table_schema = schema_cache.get(table_name, {})
        columns = [col['column_name'] for col in table_schema.get('columns', [])]
        
        enriched_desc = desc
        if columns:
            enriched_desc += f"\n\nKey fields: {', '.join(columns)}"

        ids.append(f"schema_{table_name}")
        documents.append(enriched_desc)
        metadatas.append({"table": table_name, "table_name": table_name, "type": "schema"})

    print(f"Embedding {len(ids)} descriptions into ChromaDB...")
    embeddings = embedder.encode(documents).tolist()
    collection.upsert(
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids
    )
    print("Embedding complete.")

if __name__ == "__main__":
    embed_descriptions()
