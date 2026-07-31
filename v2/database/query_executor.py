import mysql.connector
from database.connection_pool import get_connection
from config.settings import SQL_ROW_LIMIT
from config.logging import get_logger

logger = get_logger(__name__)

class QueryExecutor:
    """Executes validated SQL and formats the results."""

    def execute(self, sql: str) -> dict:
        """
        Executes SQL. 
        Returns a dictionary: {"success": bool, "rows": list, "columns": list, "error": str}
        """
        logger.info(f"Executing SQL: {sql}")
        
        # Enforce row limit
        if "LIMIT " not in sql.upper():
            sql += f" LIMIT {SQL_ROW_LIMIT}"

        conn = get_connection()
        # Using dictionary=True to return rows as dicts for easier consumption
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            columns = cursor.column_names if cursor.description else []
            
            logger.info(f"SQL execution successful. Retrieved {len(rows)} rows.")
            return {
                "success": True,
                "rows": rows,
                "columns": list(columns),
                "error": None
            }
        except mysql.connector.Error as e:
            err_msg = f"MySQL Error [{e.errno}]: {e.msg}"
            logger.error(err_msg)
            return {
                "success": False,
                "rows": [],
                "columns": [],
                "error": err_msg
            }
        finally:
            cursor.close()
            conn.close()
