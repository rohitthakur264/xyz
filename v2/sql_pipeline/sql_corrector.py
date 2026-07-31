from sql_pipeline.sql_generator import SQLGenerator
from sql_pipeline.sql_validator import SQLValidator
from database.query_executor import QueryExecutor
from config.settings import MAX_SQL_RETRIES
from config.logging import get_logger

logger = get_logger(__name__)

class SQLCorrector:
    """Manages the generation-validation-execution loop with retries."""
    
    def __init__(self, generator: SQLGenerator, validator: SQLValidator, executor: QueryExecutor):
        self.generator = generator
        self.validator = validator
        self.executor = executor

    def run_pipeline(self, question: str, plan: dict) -> dict:
        """
        Attempts to generate and execute SQL. Will retry up to MAX_SQL_RETRIES on failure.
        Returns the final execution result and metadata.
        """
        errors = []
        sql = ""
        result = None
        
        for attempt in range(1, MAX_SQL_RETRIES + 1):
            logger.info(f"SQL Pipeline Attempt {attempt}/{MAX_SQL_RETRIES}")
            
            # 1. Generate
            sql = self.generator.generate(question, plan, errors=errors)
            
            # 2. Validate (Logic/Heuristics/Schema Check)
            validation_errors = self.validator.validate(sql, plan["tables"])
            if validation_errors:
                errors = validation_errors
                logger.warning(f"Validation failed on attempt {attempt}: {errors}")
                continue # Retry immediately without hitting DB
                
            # 3. Execute (MySQL Checks)
            result = self.executor.execute(sql)
            if result["success"]:
                # Success!
                return {
                    "sql": sql,
                    "result": result,
                    "retries": attempt - 1,
                    "final_errors": []
                }
            else:
                # MySQL threw an error (e.g. Unknown Column, Syntax)
                errors = [result["error"]]
                logger.warning(f"MySQL Execution failed on attempt {attempt}: {errors}")
                
        # If we exhausted retries
        logger.error(f"SQL Pipeline failed after {MAX_SQL_RETRIES} attempts.")
        if result is None:
            err_msg = f"Validation failed: {'; '.join(errors)}" if errors else "Maximum retries exceeded."
            result = {"success": False, "rows": [], "columns": [], "error": err_msg}
        return {
            "sql": sql,
            "result": result,
            "retries": MAX_SQL_RETRIES,
            "final_errors": errors
        }
