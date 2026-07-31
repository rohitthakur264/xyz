import json
from llm.ollama_client import OllamaClient
from config.settings import ANSWER_MODEL
from config.logging import get_logger

logger = get_logger(__name__)

class AnswerGenerator:
    """Generates human-readable summaries of database results."""
    
    def __init__(self, llm_client: OllamaClient):
        self.llm = llm_client

    def generate(self, question: str, sql: str, rows: list) -> str:
        """
        Takes raw database rows and generates a friendly clinical answer.
        Does NOT hallucinate data. If rows is empty, explicitly says so.
        """
        logger.info(f"Generating answer for question: {question}")
        
        if not rows:
            return "I could not find any records matching your request in the database."
            
        # We only send a subset of rows to avoid context overflow if there are too many
        data_subset = rows[:20]
        data_str = json.dumps(data_subset, default=str, indent=2)
        
        prompt = f"""You are a clinical AI assistant for a doctor.
Your job is to answer the doctor's question based ONLY on the Data provided below.
DO NOT hallucinate or add outside medical knowledge. 
If the data is tabular, you can format it nicely.
If the data doesn't fully answer the question, state what is missing.

Question: {question}
SQL Executed (for context): {sql}

Data (up to 20 rows):
{data_str}

Answer:"""

        try:
            answer = self.llm.generate(prompt, model=ANSWER_MODEL, temperature=0.3)
            return answer.strip()
        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            return f"I found {len(rows)} matching records, but could not generate a summary."
