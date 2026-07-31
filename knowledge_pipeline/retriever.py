import chromadb
from chromadb.utils import embedding_functions
import os

CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_data")

def retrieve_chunks(question, k=5, distance_threshold=1.2):
    """
    Retrieves the top-k document chunks from knowledge_collection.
    Filters out any chunks where the distance > distance_threshold.
    Returns a list of dicts: [{'text': str, 'metadata': dict, 'distance': float}]
    """
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer('all-MiniLM-L6-v2')
    
    try:
        collection = client.get_collection(name="knowledge_collection")
    except Exception as e:
        print("Could not load Chroma collection. Did you run Phase 3 ingestor?", e)
        return []

    query_embeddings = embedder.encode([question]).tolist()
    results = collection.query(
        query_embeddings=query_embeddings,
        n_results=k
    )
    
    valid_chunks = []
    if results and results['documents'] and results['documents'][0]:
        docs = results['documents'][0]
        metas = results['metadatas'][0]
        distances = results['distances'][0]
        
        for i in range(len(docs)):
            if distances[i] <= distance_threshold:
                valid_chunks.append({
                    'text': docs[i],
                    'metadata': metas[i],
                    'distance': distances[i]
                })
                
    return valid_chunks
