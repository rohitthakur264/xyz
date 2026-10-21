import os
import requests
from database.connection_pool import get_connection
from config.settings import LLM_MODEL, SQL_MODEL, CHROMA_PERSIST_DIR, LOG_DIR
from config.logging import get_logger

logger = get_logger(__name__)

def check_mysql():
    """Check if MySQL connection pool is healthy."""
    try:
        conn = get_connection()
        if conn.is_connected():
            conn.close()
            return True
        return False
    except Exception as e:
        logger.error(f"MySQL health check failed: {e}")
        return False

def check_groq():
    """Check if GROQ API key is present."""
    import os
    from config.settings import LLM_API_KEY
    if LLM_API_KEY:
        return True
    
    # Check for rotated keys
    for k, v in os.environ.items():
        if k.startswith("LLM_API_KEY_") and v.strip():
            return True
            
    logger.error("No LLM_API_KEY or LLM_API_KEY_n is set.")
    return False

def check_directories():
    """Verify required directories exist and create them if they don't."""
    required = [CHROMA_PERSIST_DIR, LOG_DIR]
    missing = []
    for d in required:
        if not os.path.exists(d):
            try:
                os.makedirs(d, exist_ok=True)
                logger.info(f"Created missing directory: {d}")
            except Exception as e:
                logger.error(f"Failed to create directory {d}: {e}")
                missing.append(d)
    if missing:
        return False
    return True

def run_health_checks():
    """Run all startup health checks and exit if critical failure."""
    logger.info("Running startup health checks...")
    
    # Map of component -> (check_func, is_critical)
    checks = {
        "Directories": (check_directories, True),
        "MySQL": (check_mysql, False),
        "Groq": (check_groq, True),
    }
    
    failed_critical = []
    for name, (check_func, is_critical) in checks.items():
        if check_func():
            logger.info(f"[OK] {name}")
        else:
            if is_critical:
                logger.error(f"[FAILED] {name}")
                failed_critical.append(name)
            else:
                logger.warning(f"[WARNING] {name} check failed. Application will operate with cached schema fallback.")
            
    if failed_critical:
        logger.critical(f"Startup checks failed for: {failed_critical}. Stopping execution.")
        raise RuntimeError(f"Health checks failed: {failed_critical}")
    
    logger.info("All critical health checks passed. System is ready.")
