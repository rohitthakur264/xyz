import re
from llm.ollama_client import OllamaClient
from llm.prompt_builder import (
    SYSTEM_PROMPT, BUSINESS_RULES, build_schema_section, 
    build_examples_section, build_context_section, build_error_correction_section
)
from config.settings import SQL_MODEL
from config.logging import get_logger

logger = get_logger(__name__)

class SQLGenerator:
    """Generates SQL using Ollama."""
    
    def __init__(self, llm_client: OllamaClient, full_schema_cache: dict):
        self.llm = llm_client
        self.schema_cache = full_schema_cache

    def generate(self, question: str, plan: dict, errors: list = None) -> str:
        """Generates SQL based on the question, the query plan, and optional errors."""
        logger.info(f"Generating SQL for question: {question}")
        
        prompt = f"{SYSTEM_PROMPT}\n\n"
        prompt += f"{BUSINESS_RULES}\n\n"
        prompt += build_schema_section(plan["tables"], self.schema_cache) + "\n"
        prompt += build_examples_section(plan["examples"]) + "\n"
        prompt += build_context_section(plan["session_context"]) + "\n"
        prompt += build_error_correction_section(errors) + "\n"
        
        prompt += f"### Task\nQuestion: {question}\nSQL:"
        
        raw_sql = self.llm.generate(prompt, model=SQL_MODEL, temperature=0.1)
        return self.clean_sql(raw_sql)

    def clean_sql(self, raw_sql: str) -> str:
        """Strips markdown and sanitizes the output."""
        sql = raw_sql.strip()
        # Remove markdown code blocks if the model hallucinates them
        sql = re.sub(r"```sql\s*(.*?)\s*```", r"\1", sql, flags=re.DOTALL)
        sql = re.sub(r"```\s*(.*?)\s*```", r"\1", sql, flags=re.DOTALL)
        
        # Remove any leading 'sql' keyword
        if sql.lower().startswith("sql\n"):
            sql = sql[4:].strip()
            
        # Ensure single line or clean whitespace
        sql = sql.replace('\n', ' ').strip()
        
        # Remove trailing semicolon for uniformity (we can add it later if needed)
        if sql.endswith(';'):
            sql = sql[:-1]
            
        return sql
