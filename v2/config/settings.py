import os
from dotenv import load_dotenv

load_dotenv(override=True)

# LLM settings
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("GROQ_API", ""))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1/chat/completions")
ANSWER_MODEL = os.getenv("ANSWER_MODEL", "openai/gpt-oss-120b").strip()
LLM_MODEL = ANSWER_MODEL
SQL_MODEL = os.getenv("SQL_MODEL", "openai/gpt-oss-120b").strip()
FAST_MODEL = os.getenv("FAST_MODEL", "openai/gpt-oss-20b").strip()
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))

# Database Configuration
DB_HOST = os.getenv("DB_HOST", os.getenv("MYSQL_HOST", "localhost"))
DB_PORT = int(os.getenv("DB_PORT", os.getenv("MYSQL_PORT", "3306")))
DB_USER = os.getenv("DB_USER", os.getenv("MYSQL_USER", "root"))
DB_PASSWORD = os.getenv("DB_PASSWORD", os.getenv("MYSQL_PASSWORD", ""))
DB_NAME = os.getenv("DB_NAME", os.getenv("MYSQL_DATABASE", ""))

if not DB_NAME:
    raise RuntimeError(
        "DB_NAME is not set. Please configure DB_NAME in your .env file before starting the server."
    )
DB_POOL_NAME = "hospital_pool"
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "15"))

# Schema Filtering Settings
IGNORE_COLUMN_PREFIXES = os.getenv("IGNORE_COLUMN_PREFIXES", "old,bak,tmp").split(",")
IGNORE_COLUMNS = os.getenv("IGNORE_COLUMNS", "created_by,updated_by,machine_name,inserted_by,inserted_ipaddress,inserted_macid,inserted_macname,inserted_on,updated_ipaddress,updated_macid,updated_macname,updated_on,client_id,center_id,je,flag").split(",")
AUDIT_PREFIXES = os.getenv("AUDIT_PREFIXES", "inserted,updated,cancelled,macid,ipaddress").split(",")

# Database Pipeline Settings
SQL_ROW_LIMIT = int(os.getenv("SQL_ROW_LIMIT", "50"))
SCHEMA_RETRIEVAL_K = int(os.getenv("SCHEMA_RETRIEVAL_K", "5"))
MAX_SQL_RETRIES = int(os.getenv("MAX_SQL_RETRIES", "3"))

# Knowledge Pipeline Settings
RAG_RETRIEVAL_K = int(os.getenv("RAG_RETRIEVAL_K", "5"))
RAG_DISTANCE_THRESHOLD = float(os.getenv("RAG_DISTANCE_THRESHOLD", "1.2"))

# Directories
V2_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(V2_DIR)

_raw_chroma_dir = os.getenv("CHROMA_PERSIST_DIR", "chroma_data")
if os.path.isabs(_raw_chroma_dir):
    CHROMA_PERSIST_DIR = _raw_chroma_dir
else:
    CHROMA_PERSIST_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, _raw_chroma_dir))

SCHEMA_CACHE_FILE = os.getenv("SCHEMA_CACHE_FILE", os.path.join(PROJECT_ROOT, "schema_intel", "schema_cache.json"))

# Debugging
DEBUG_MODE = os.getenv("DEBUG_MODE", "True").lower() in ("true", "1", "yes")

# Logging
LOG_DIR = os.getenv("LOG_DIR", "logs")
INTERACTION_LOG_FILE = f"{LOG_DIR}/interaction_log.jsonl"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ENABLE_WRITE_OPERATIONS = True
