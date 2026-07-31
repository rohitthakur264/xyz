import json
import os
from database.connection_pool import get_connection
from config.settings import DB_NAME, IGNORE_COLUMN_PREFIXES, IGNORE_COLUMNS
from config.logging import get_logger

logger = get_logger(__name__)

class SchemaLoader:
    """Loads and sanitizes the database schema."""
    
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name

    def should_ignore_column(self, col_name: str) -> bool:
        col_lower = col_name.lower()
        if col_lower in IGNORE_COLUMNS:
            return True
        for prefix in IGNORE_COLUMN_PREFIXES:
            if prefix and col_lower.startswith(prefix):
                return True
        return False

    def load_schema(self) -> dict:
        """Loads tables, columns, PKs, and FKs from INFORMATION_SCHEMA, applying filtering."""
        logger.info(f"Loading schema for database: {self.db_name}")
        schema = {}
        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            # 1. Load Tables
            cursor.execute("""
                SELECT TABLE_NAME, TABLE_COMMENT 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
            """, (self.db_name,))
            for row in cursor.fetchall():
                t_name = row['TABLE_NAME']
                schema[t_name] = {
                    "table": t_name,
                    "description": row['TABLE_COMMENT'] or f"Table storing {t_name} data",
                    "columns": [],
                    "primary_key": None,
                    "foreign_keys": [],
                    "relationships": [],
                    "examples": []
                }
                
            # 2. Load Columns
            cursor.execute("""
                SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, COLUMN_KEY 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s
                ORDER BY ORDINAL_POSITION
            """, (self.db_name,))
            for row in cursor.fetchall():
                t_name = row['TABLE_NAME']
                c_name = row['COLUMN_NAME']
                if t_name in schema and not self.should_ignore_column(c_name):
                    schema[t_name]["columns"].append({
                        "column_name": c_name,
                        "data_type": row['DATA_TYPE']
                    })
                    if row['COLUMN_KEY'] == 'PRI':
                        schema[t_name]["primary_key"] = c_name

            # 3. Load Foreign Keys
            cursor.execute("""
                SELECT 
                    TABLE_NAME, 
                    COLUMN_NAME, 
                    REFERENCED_TABLE_NAME, 
                    REFERENCED_COLUMN_NAME 
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
                WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL
            """, (self.db_name,))
            for row in cursor.fetchall():
                t_name = row['TABLE_NAME']
                c_name = row['COLUMN_NAME']
                r_table = row['REFERENCED_TABLE_NAME']
                r_col = row['REFERENCED_COLUMN_NAME']
                
                if t_name in schema and r_table in schema:
                    if not self.should_ignore_column(c_name) and not self.should_ignore_column(r_col):
                        schema[t_name]["foreign_keys"].append({
                            "column_name": c_name,
                            "referenced_table": r_table,
                            "referenced_column": r_col
                        })
            
            # 4. Remove tables that ended up with no columns after filtering (rare, but good to clean)
            schema = {k: v for k, v in schema.items() if len(v["columns"]) > 0}
            
            logger.info(f"Loaded and sanitized {len(schema)} tables.")
            return schema

        except Exception as e:
            logger.warning(f"Error connecting to database ({e}). Falling back to cached schema...")
            from config.settings import SCHEMA_CACHE_FILE
            if os.path.exists(SCHEMA_CACHE_FILE):
                with open(SCHEMA_CACHE_FILE, 'r') as f:
                    raw_schema = json.load(f)
                sanitized_schema = {}
                for t, info in raw_schema.items():
                    info_copy = dict(info)
                    info_copy["columns"] = [c for c in info.get("columns", []) if not self.should_ignore_column(c["column_name"])]
                    if len(info_copy["columns"]) > 0:
                        sanitized_schema[t] = info_copy
                logger.info(f"Loaded and sanitized {len(sanitized_schema)} tables from schema cache file: {SCHEMA_CACHE_FILE}")
                return sanitized_schema
            logger.error(f"Error loading schema and schema cache not found: {e}")
            raise
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
            if 'conn' in locals() and conn:
                conn.close()

if __name__ == "__main__":
    loader = SchemaLoader()
    s = loader.load_schema()
    print(f"Loaded {len(s)} tables.")
