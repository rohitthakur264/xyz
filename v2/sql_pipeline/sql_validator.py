import re
from config.logging import get_logger

logger = get_logger(__name__)

class SQLValidator:
    """Validates generated SQL before execution."""
    
    def __init__(self, full_schema_cache: dict):
        self.schema_cache = full_schema_cache

    def validate(self, sql: str, allowed_tables: list) -> list:
        """
        Runs a suite of checks on the SQL string.
        Returns a list of error strings. Empty list means the SQL is valid.
        """
        errors = []
        sql_lower = sql.lower()

        # 1. Dangerous SQL Check
        forbidden_keywords = ["drop", "delete", "update", "insert", "alter", "truncate", "grant", "revoke"]
        # Basic word boundary check
        for kw in forbidden_keywords:
            if re.search(rf"\b{kw}\b", sql_lower):
                errors.append(f"DANGEROUS SQL detected. The keyword '{kw.upper()}' is not allowed in a SELECT query.")

        if not sql_lower.startswith("select"):
            errors.append("Query must start with SELECT.")

        # 2. Table Check
        # Extract table names referenced after FROM or JOIN
        table_matches = re.findall(r"\b(?:from|join)\s+([a-zA-Z_0-9]+)\b", sql_lower)
        referenced_tables = [t for t in table_matches]
        
        for table in referenced_tables:
            if table not in allowed_tables:
                errors.append(f"Table '{table}' was used in the query, but it is not in the allowed schema context. The LLM Hallucinated it.")

        # 3. Syntax / Heuristics Check
        if " = = " in sql:
            errors.append("Syntax Error: Found ' = = '. Did you mean ' = '?")
        if sql.count("(") != sql.count(")"):
            errors.append("Syntax Error: Mismatched parentheses.")

        if errors:
            logger.warning(f"SQL Validation failed with {len(errors)} errors: {errors}")
        else:
            logger.info("SQL Validation passed.")
            
        return errors
