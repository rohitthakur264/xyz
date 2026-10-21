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
        try:
            results = self.vector_store.schema_collection.query(
                query_embeddings=self.vector_store._get_embeddings([question]),
                n_results=k
            )
        except Exception as e:
            # A RAG/Chroma failure must never crash a chat request.
            logger.warning(f"Schema retrieval failed ({e}); continuing with keyword tables only.")
            results = {}

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
                if tbl and tbl not in tables:
                    tables.append(tbl)

        logger.info(f"Retrieved {len(tables)} tables: {tables}")
        return tables
