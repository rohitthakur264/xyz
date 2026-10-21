import mysql.connector
from mysql.connector import pooling
from config.settings import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_POOL_NAME, DB_POOL_SIZE
from config.logging import get_logger

logger = get_logger(__name__)

# Global connection pool
_pool = None

def init_pool():
    global _pool
    if _pool is None:
        try:
            logger.info(f"Initializing MySQL Connection Pool: {DB_POOL_NAME} (Size: {DB_POOL_SIZE})")
            _pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name=DB_POOL_NAME,
                pool_size=DB_POOL_SIZE,
                pool_reset_session=False,
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                compress=True
            )
            logger.info("Connection pool initialized successfully.")
        except mysql.connector.Error as err:
            logger.error(f"Failed to initialize connection pool: {err}")
            raise

def get_connection():
    """Get a connection from the pool."""
    global _pool
    if _pool is None:
        init_pool()
    try:
        return _pool.get_connection()
    except mysql.connector.Error as err:
        logger.error(f"Failed to get connection from pool: {err}")
        raise
