import sys
import os

from sql_pipeline.retriever import retrieve_tables
from sql_pipeline.generator import generate_and_execute_sql
from sql_pipeline.answerer import answer_question
from config.settings import SCHEMA_RETRIEVAL_K

def execute_sql_pipeline(question: str, active_patient: str = None) -> dict:
    """Runs the DB pipeline and returns a dictionary with the results."""
    # Step 1: Retrieving tables
    retrieved_schema = retrieve_tables(question, k=SCHEMA_RETRIEVAL_K)
    
    if not retrieved_schema:
        return {
            "answer": "No relevant tables found.",
            "sql_used": None,
            "error": "No tables retrieved",
            "debug_info": {"retrieved_tables": []}
        }
        
    # Step 2-4: Generate, Validate, Execute SQL
    sql_used, rows, columns, error_msg, attempts_debug = generate_and_execute_sql(question, retrieved_schema, active_patient=active_patient)
    
    debug_info = {
        "retrieved_tables": list(retrieved_schema.keys()),
        "attempts": attempts_debug,
        "final_sql": sql_used,
        "row_count": len(rows) if rows else 0
    }

    if error_msg:
        return {
            "answer": f"Error during SQL generation/execution: {error_msg}",
            "sql_used": None,
            "error": error_msg,
            "debug_info": debug_info
        }
        
    # Step 5: Generate grounded answer
    final_answer = answer_question(question, sql_used, columns, rows)
    
    # String-convert row values to prevent JSON serialization errors
    stringified_rows = [[str(v) for v in row] for row in rows] if rows else []

    return {
        "answer": final_answer,
        "sql_used": sql_used,
        "rows": stringified_rows,
        "columns": columns,
        "error": None,
        "debug_info": debug_info
    }

def run_phase2():
    print("=== Phase 2: Text-to-SQL Pipeline ===")
    
    question = input("\nEnter a natural language question about the database: ")
    if not question.strip():
        print("Empty question. Exiting.")
        sys.exit(0)
        
    print("\n[Step 1] Retrieving relevant tables from ChromaDB...")
    result = execute_sql_pipeline(question)
    
    if result["error"]:
        print(result["answer"])
    else:
        if result["sql_used"]:
            print(f"\n> Validated SQL Executed:\n{result['sql_used']}\n")
        
        print("[Step 5] Generating grounded answer...")
        print("\n=== Final Answer ===")
        print(result["answer"])
        print("====================")

if __name__ == "__main__":
    run_phase2()
