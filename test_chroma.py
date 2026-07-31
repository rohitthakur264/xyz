import chromadb
from chromadb.utils import embedding_functions

def test():
    client = chromadb.PersistentClient('./chroma_data')
    ollama_ef = embedding_functions.OllamaEmbeddingFunction(
        url="http://localhost:11434/api/embeddings",
        model_name="nomic-embed-text"
    )
    col = client.get_collection('schema_collection', embedding_function=ollama_ef)
    results = col.query(query_texts=["registration no 165881"], n_results=15)
    print("Top 15 tables:")
    for doc_id, dist in zip(results['ids'][0], results['distances'][0]):
        print(f"{doc_id}: {dist}")

if __name__ == "__main__":
    test()
