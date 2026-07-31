import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.connection import get_db_connection

def execute_sql(sql_query):
    """
    Execute the validated SQL query against the read-only connection.
    Returns (columns, rows, None) on success, or (None, None, error_msg) on failure.
    """
    conn = get_db_connection()
    if not conn:
        return None, None, "Database connection failed."

    try:
        cursor = conn.cursor()
        try:
            cursor.execute("SET SESSION max_statement_time=15")  # seconds; kills runaway queries
        except Exception:
            pass # Ignore if DB does not support this variable
        cursor.execute(sql_query)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return columns, rows, None
    except Exception as e:
        return None, None, str(e)
    finally:
        if conn.is_connected():
            conn.close()
