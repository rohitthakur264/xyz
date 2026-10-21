import re
from llm.llm_client import LLMClient
from llm.prompt_builder import (
    SYSTEM_PROMPT, build_business_rules, build_schema_section, build_joins_section,
    build_examples_section, build_context_section, build_error_correction_section
)
from config.settings import SQL_MODEL
from config.logging import get_logger

logger = get_logger(__name__)

class SQLGenerator:
    """Generates SQL using Ollama."""
    
    def __init__(self, llm_client: LLMClient, full_schema_cache: dict):
        self.llm = llm_client
        self.schema_cache = full_schema_cache

    def generate(self, question: str, plan: dict, errors: list = None) -> str:
        """Generates SQL based on the question, the query plan, and optional errors."""
        logger.info(f"Generating SQL for question: {question}")
        
        prompt = f"{SYSTEM_PROMPT}\n\n"
        prompt += build_business_rules(self.schema_cache, plan.get("intent")) + "\n\n"
        prompt += build_schema_section(plan["tables"], self.schema_cache) + "\n"
        prompt += build_joins_section(plan.get("joins", [])) + "\n"
        prompt += build_examples_section(plan["examples"]) + "\n"
        prompt += build_context_section(plan["session_context"]) + "\n"
        prompt += build_error_correction_section(errors) + "\n"
        
        prompt += f"### Task\nQuestion: {question}\nSQL:"
        
        raw_sql = self.llm.generate(prompt, model=SQL_MODEL, temperature=0.1)
        return self.clean_sql(raw_sql)

    def clean_sql(self, raw_sql: str) -> str:
        """Strips markdown, leading prose, and trailing explanation from the output."""
        sql = raw_sql.strip()

        # Some models use <think> tags for CoT
        sql = re.sub(r"<think>.*?</think>\n*", "", sql, flags=re.DOTALL)
        
        # If the model used markdown, extract the LAST sql block
        matches = re.findall(r"```(?:sql)?\s*(.*?)\s*```", sql, flags=re.DOTALL | re.IGNORECASE)
        if matches:
            sql = matches[-1].strip()

        # Remove any leading 'sql' keyword if it leaked from markdown
        if sql.lower().startswith("sql\n"):
            sql = sql[4:].strip()

        # The model sometimes wraps the query in explanatory prose even without markdown.
        # Find the LAST SELECT statement to skip the "Chain of Thought" text
        idx = sql.upper().rfind("SELECT ")
        if idx != -1:
            sql = sql[idx:].strip()

        # Strip standard SQL comments if they cause issues when flattened later
        lines = []
        for line in sql.splitlines():
            line = line.strip()
            if not line.startswith("--") and not line.startswith("//"):
                lines.append(line)
        sql = " ".join(lines).strip()

        # Trim anything after the statement terminator
        semi = sql.find(';')
        if semi != -1:
            sql = sql[:semi].strip()

        # Remove trailing markdown if model forgot closing tag
        if sql.endswith("```"):
            sql = sql[:-3].strip()

        return sql
