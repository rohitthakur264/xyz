from rag.vector_store import VectorStore
from config.settings import RAG_RETRIEVAL_K
from config.logging import get_logger

logger = get_logger(__name__)

class ExampleRetriever:
    """Retrieves relevant SQL examples based on the question and intent."""
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        
    def retrieve_examples(self, question: str, intent: str = "GENERAL", k: int = RAG_RETRIEVAL_K) -> list:
        """
        Retrieves the top k SQL examples.
        """
        logger.info(f"Retrieving SQL examples for: '{question}' (Intent: {intent})")
        
        # We can add a where clause based on intent if it's not GENERAL
        where_clause = None
        if intent != "GENERAL":
            where_clause = {"intent": intent}
            
        try:
            results = self.vector_store.example_collection.query(
                query_embeddings=self.vector_store._get_embeddings([question]),
                n_results=k,
                where=where_clause
            )
        except Exception as e:
            # A RAG/Chroma failure must never crash a chat request.
            logger.warning(f"Example retrieval failed ({e}); continuing without examples.")
            return []

        examples = []
        if results and results.get("metadatas") and len(results["metadatas"]) > 0:
            documents = results.get("documents", [[]])[0] if results.get("documents") else []
            for idx, metadata in enumerate(results["metadatas"][0]):
                if metadata:
                    examples.append({
                        "question": documents[idx] if idx < len(documents) else "",
                        "sql": metadata.get("sql"),
                        "tables": metadata.get("tables", "").split(",")
                    })
                    
        logger.info(f"Retrieved {len(examples)} SQL examples.")
        return examples
