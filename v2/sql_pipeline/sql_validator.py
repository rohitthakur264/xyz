import re
from config.logging import get_logger

logger = get_logger(__name__)

class SQLValidator:
    """Validates generated SQL before execution."""

    def __init__(self, full_schema_cache: dict, graph=None):
        self.schema_cache = full_schema_cache
        self.graph = graph

    def _patient_link_hint(self, table: str, allowed_tables: list) -> str:
        """When a table is missing a patient column, tell the model the verified join
        path to reach the patient (schema-derived, never hardcoded).

        Only fires when the path is short and every table on it is already in the
        allowed context, so we never suggest an unverifiable multi-hop detour.
        """
        if not self.graph:
            return ""
        from database.schema_anchors import find_anchor_tables
        patient = find_anchor_tables(self.schema_cache).get("patient")
        if not patient or table == patient:
            return ""
        path = self.graph.find_shortest_path(table, patient)
        if not path or len(path) < 2 or len(path) > 3:
            return ""
        joins = self.graph.get_join_conditions(path)
        if not joins:
            return ""
        return (
            f"This table is not directly linked to the patient. To filter by patient "
            f"you MUST join through: {'; '.join(joins)}."
        )

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
        
        schema_cache_lower = {}
        for k in self.schema_cache.keys():
            if k.lower() not in schema_cache_lower:
                schema_cache_lower[k.lower()] = k
            # If there's a collision (e.g. fhir_service_mst vs fhir_Service_mst), 
            # we keep the first one for lowercase fallback, but exact match will win below.

        for table in referenced_tables:
            actual_table = table if table in self.schema_cache else schema_cache_lower.get(table.lower())
            if not actual_table:
                errors.append(f"Table '{table}' does not exist in the database. The LLM Hallucinated it.")

        # Build the alias -> table map once (reused by column and join checks).
        # The optional alias capture must NOT swallow the next SQL keyword
        # (e.g. treat "JOIN" after a bare table name as that table's alias).
        alias_map = {}
        _reserved = (r"(?:from|join|where|on|and|or|group|order|limit|having|as|set|union|select"
                     r"|inner|left|right|full|cross|outer)")
        for m in re.finditer(
            rf"\b(?:from|join)\s+([a-zA-Z_0-9]+)(?:\s+(?:AS\s+)?(?!{_reserved})\b([a-zA-Z_0-9]+))?",
            sql_lower,
        ):
            table = m.group(1)
            alias = m.group(2) or table
            alias_map[alias] = table

        # 2b. Column Check (alias + full table name) - catches hallucinated columns early
        #      so the corrector gets a precise, actionable error instead of a MySQL 1054.
        for alias, table in alias_map.items():
            actual_table = table if table in self.schema_cache else schema_cache_lower.get(table.lower())
            if not actual_table:
                continue
            original_table_name = actual_table
            schema_cols = {c["column_name"].lower() for c in self.schema_cache[original_table_name]["columns"]}
            refs = set()
            refs.update(m.group(1) for m in re.finditer(rf"\b{re.escape(alias)}\.([a-zA-Z_0-9]+)", sql_lower))
            refs.update(m.group(1) for m in re.finditer(rf"\b{re.escape(table)}\.([a-zA-Z_0-9]+)", sql_lower))
            for col in refs:
                if col not in schema_cols:
                    avail = ", ".join(sorted(schema_cols))
                    msg = (
                        f"Column '{col}' does not exist in table '{table}'. "
                        f"Available columns: {avail[:300]}"
                    )
                    link_hint = self._patient_link_hint(table, allowed_tables)
                    if link_hint:
                        msg += " " + link_hint
                    errors.append(msg)

        # 2c. Join Path Check - catches a direct join that bypasses a verified multi-hop path.
        if self.graph:
            for m in re.finditer(
                r"\bon\s+([a-zA-Z_0-9]+)\.([a-zA-Z_0-9]+)\s*=\s*([a-zA-Z_0-9]+)\.([a-zA-Z_0-9]+)",
                sql_lower,
            ):
                t1 = alias_map.get(m.group(1), m.group(1))
                t2 = alias_map.get(m.group(3), m.group(3))
                if t1 not in self.schema_cache or t2 not in self.schema_cache:
                    continue
                if self.graph.graph.has_edge(t1, t2):
                    continue  # direct join matches a known edge -> fine
                path = self.graph.find_shortest_path(t1, t2)
                # Only flag when the path is short to avoid massive multi-hop hints
                if not path or len(path) > 3:
                    continue
                joins = self.graph.get_join_conditions(path)
                if not joins:
                    continue
                errors.append(
                    f"Tables '{t1}' and '{t2}' are NOT directly related. You joined them directly, "
                    f"but the verified path to connect them is: {'; '.join(joins)}. "
                    f"Rewrite the query to join through this full path."
                )

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
