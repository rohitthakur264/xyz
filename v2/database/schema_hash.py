import hashlib
import json
import os
from config.settings import SCHEMA_CACHE_FILE
from config.logging import get_logger

logger = get_logger(__name__)

class SchemaHasher:
    """Manages schema versioning via hashing."""
    
    def __init__(self, cache_file: str = SCHEMA_CACHE_FILE):
        self.cache_file = cache_file

    def compute_hash(self, schema: dict) -> str:
        """Compute MD5 hash of the current schema dict."""
        schema_str = json.dumps(schema, sort_keys=True).encode('utf-8')
        return hashlib.md5(schema_str).hexdigest()

    def get_cached_hash(self) -> str:
        """Retrieve the hash of the previously cached schema."""
        if not os.path.exists(self.cache_file):
            return None
        try:
            with open(self.cache_file, "r") as f:
                data = json.load(f)
                return data.get("_metadata", {}).get("schema_hash")
        except Exception as e:
            logger.warning(f"Could not read schema hash: {e}")
            return None

    def save_cache(self, schema: dict, schema_hash: str):
        """Save the schema to disk with its hash."""
        data = {
            "_metadata": {
                "schema_hash": schema_hash
            },
            "schema": schema
        }
        with open(self.cache_file, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Schema cached to {self.cache_file} with hash {schema_hash}")

    def load_cache(self) -> dict:
        """Load the cached schema data."""
        if not os.path.exists(self.cache_file):
            return None
        try:
            with open(self.cache_file, "r") as f:
                return json.load(f).get("schema")
        except Exception:
            return None
