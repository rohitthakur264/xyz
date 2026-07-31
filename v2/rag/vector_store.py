import chromadb
from sentence_transformers import SentenceTransformer
from config.settings import CHROMA_PERSIST_DIR
from config.logging import get_logger

logger = get_logger(__name__)

class VectorStore:
    """Manages the two Chroma collections: schema and examples."""
    
    def __init__(self, persist_dir=CHROMA_PERSIST_DIR):
        self.persist_dir = persist_dir
        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Collection 1: Schema
        self.schema_collection = self.client.get_or_create_collection(
            name="schema_collection",
            metadata={"description": "Database Schema and Table metadata"}
        )
        
        # Collection 2: Examples
        self.example_collection = self.client.get_or_create_collection(
            name="example_collection",
            metadata={"description": "Curated SQL Examples"}
        )
        
    def _get_embeddings(self, texts: list) -> list:
        return self.embedding_model.encode(texts).tolist()

    def update_schema(self, table_texts: dict, metadata_dicts: dict):
        """Rebuild the schema collection. table_texts = {table_name: text}"""
        logger.info(f"Updating Schema Collection with {len(table_texts)} tables...")
        
        if len(table_texts) == 0:
            return
            
        # Delete existing schema records
        existing_ids = self.schema_collection.get()['ids']
        if existing_ids:
            self.schema_collection.delete(ids=existing_ids)
            
        tables = list(table_texts.keys())
        texts = [table_texts[t] for t in tables]
        metadatas = []
        for t in tables:
            m = dict(metadata_dicts.get(t, {}))
            m["table"] = t
            m["table_name"] = t
            metadatas.append(m)
        ids = [f"schema_{t}" for t in tables]
        
        embeddings = self._get_embeddings(texts)
        
        self.schema_collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )
        logger.info("Schema Collection updated successfully.")

    def update_examples(self, examples: list):
        """Rebuild the example collection. examples is a list of dicts with 'intent', 'question', 'sql', 'tables'."""
        logger.info(f"Updating Example Collection with {len(examples)} examples...")
        
        if len(examples) == 0:
            return
            
        # Delete existing examples
        existing_ids = self.example_collection.get()['ids']
        if existing_ids:
            self.example_collection.delete(ids=existing_ids)
            
        texts = [ex['question'] for ex in examples]
        # We store the SQL as part of the metadata so it can be retrieved without parsing the document
        metadatas = [{
            "intent": ex.get("intent", "GENERAL"),
            "sql": ex["sql"],
            "tables": ",".join(ex.get("tables", []))
        } for ex in examples]
        ids = [f"example_{i}" for i in range(len(examples))]
        
        embeddings = self._get_embeddings(texts)
        
        self.example_collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )
        logger.info("Example Collection updated successfully.")
