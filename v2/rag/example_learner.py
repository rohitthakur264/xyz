import json
import os
import re
from config.settings import LOG_DIR
from config.logging import get_logger

logger = get_logger(__name__)

# Matches the audit log written by config.logging.AuditLogger
AUDIT_LOG_FILE = os.path.join(LOG_DIR, "audit_log.jsonl")


class ExampleLearner:
    """
    Dynamically learns SQL few-shot examples from the audit log of *successful*
    query executions. This is the data-driven counterpart to hardcoded examples:
    every example here was executed against the real database and returned rows,
    so it is grounded in the actual schema instead of an imagined one.
    """

    def __init__(self, vector_store, full_schema_cache: dict):
        self.vector_store = vector_store
        self.schema_cache = full_schema_cache

    @staticmethod
    def _extract_tables(sql: str) -> list:
        """Pull the table names referenced in FROM / JOIN clauses."""
        tables = []
        for m in re.findall(r"\b(?:from|join)\s+([a-zA-Z_0-9]+)\b", sql, re.IGNORECASE):
            if m not in tables:
                tables.append(m)
        return tables

    def _tables_exist(self, tables: list) -> bool:
        """Only learn examples whose tables actually exist in the schema."""
        return all(t in self.schema_cache for t in tables)

    def learn(self) -> int:
        """
        Rebuild the Chroma example collection from validated audit-log records.
        Returns the number of examples learned. No-op if the log is absent or empty.
        """
        if not os.path.exists(AUDIT_LOG_FILE):
            logger.info(f"No audit log at {AUDIT_LOG_FILE}; skipping example learning.")
            return 0

        examples = []
        seen = set()
        with open(AUDIT_LOG_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                sql = (rec.get("generated_sql") or "").strip()
                question = (rec.get("question") or "").strip()
                intent = rec.get("intent") or "GENERAL"

                # Keep only queries that ran cleanly and returned data.
                if not sql.lower().startswith("select"):
                    continue
                if rec.get("validation_errors"):
                    continue
                if int(rec.get("rows_returned", 0) or 0) <= 0:
                    continue

                tables = self._extract_tables(sql)
                if not tables or not self._tables_exist(tables):
                    logger.debug(f"Skipping example referencing unknown tables: {tables}")
                    continue

                key = (question.lower(), sql.lower())
                if key in seen:
                    continue
                seen.add(key)
                examples.append({
                    "intent": intent,
                    "question": question,
                    "sql": sql,
                    "tables": tables,
                })

        if examples:
            self.vector_store.update_examples(examples)
            logger.info(f"Learned {len(examples)} examples from audit log into Chroma.")
        else:
            logger.info("No learnable examples found in audit log.")
        return len(examples)
