import mysql.connector
import sqlparse
from database.connection_pool import get_connection
from config.settings import SQL_ROW_LIMIT
from config.logging import get_logger

logger = get_logger(__name__)

def _has_top_level_limit(sql: str) -> bool:
    parsed = sqlparse.parse(sql)[0]
    tokens = [t for t in parsed.tokens if not t.is_whitespace]
    return any(t.ttype is sqlparse.tokens.Keyword and t.value.upper() == "LIMIT" for t in tokens)

class QueryExecutor:
    """Executes validated SQL and formats the results."""

    def execute(self, sql: str) -> dict:
        """
        Executes SQL. 
        Returns a dictionary: {"success": bool, "rows": list, "columns": list, "error": str}
        """
        logger.info(f"Executing SQL: {sql}")
        
        # Enforce row limit
        if not _has_top_level_limit(sql):
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
            if e.errno == 1267:
                logger.warning("1267 Collation mismatch hit. Auto-fixing query with COLLATE utf8mb4_unicode_ci...")
                import re
                fixed_sql = re.sub(
                    r'(\b\w+\.allergy)\s*=\s*(\b\w+\.code)',
                    r'\1 COLLATE utf8mb4_unicode_ci = \2 COLLATE utf8mb4_unicode_ci',
                    sql,
                    flags=re.IGNORECASE
                )
                if fixed_sql != sql:
                    try:
                        cursor.execute(fixed_sql)
                        rows = cursor.fetchall()
                        columns = cursor.column_names if cursor.description else []
                        logger.info(f"Collation auto-fix succeeded. Retrieved {len(rows)} rows.")
                        return {
                            "success": True,
                            "rows": rows,
                            "columns": list(columns),
                            "error": None
                        }
                    except Exception as retry_err:
                        logger.error(f"Collation retry failed: {retry_err}")

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

    def execute_prepared(self, sql: str, params: tuple) -> dict:
        """
        Executes parameterized SQL. 
        Returns a dictionary: {"success": bool, "rows": list, "columns": list, "error": str}
        """
        logger.info(f"Executing Prepared SQL: {sql} with params {params}")
        
        if not _has_top_level_limit(sql):
            sql += f" LIMIT {SQL_ROW_LIMIT}"

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            columns = cursor.column_names if cursor.description else []
            
            logger.info(f"Prepared SQL execution successful. Retrieved {len(rows)} rows.")
            return {
                "success": True,
                "rows": rows,
                "columns": list(columns),
                "error": None
            }
        except mysql.connector.Error as e:
            if e.errno == 1267:
                logger.warning("1267 Collation mismatch hit in prepared query. Auto-fixing with COLLATE utf8mb4_unicode_ci...")
                import re
                fixed_sql = re.sub(
                    r'(\b\w+\.allergy)\s*=\s*(\b\w+\.code)',
                    r'\1 COLLATE utf8mb4_unicode_ci = \2 COLLATE utf8mb4_unicode_ci',
                    sql,
                    flags=re.IGNORECASE
                )
                if fixed_sql != sql:
                    try:
                        cursor.execute(fixed_sql, params)
                        rows = cursor.fetchall()
                        columns = cursor.column_names if cursor.description else []
                        logger.info(f"Collation auto-fix in prepared query succeeded. Retrieved {len(rows)} rows.")
                        return {
                            "success": True,
                            "rows": rows,
                            "columns": list(columns),
                            "error": None
                        }
                    except Exception as retry_err:
                        logger.error(f"Prepared collation retry failed: {retry_err}")

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
