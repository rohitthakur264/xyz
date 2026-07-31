import os
import json
import ollama
from config.settings import LLM_MODEL, LLM_TEMPERATURE
import sys

# Ensure extractor can be imported when running from the root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from schema_intel.extractor import cache_schema

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "table_descriptions.json")

def generate_descriptions():
    """
    Idempotent function that checks for missing descriptions in table_descriptions.json
    and uses Ollama to generate plain English summaries of those tables.
    """
    existing_descriptions = {}
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r') as f:
                existing_descriptions = json.load(f)
        except json.JSONDecodeError:
            pass

    schema = cache_schema()
    if not schema:
        print("No schema extracted. Check DB connection.")
        return

    updated = False
    for table_name, table_info in schema.items():
        columns = table_info['columns']
        if table_name in existing_descriptions:
            print(f"Skipping {table_name}: Description already exists.")
            continue
            
        print(f"Generating description for {table_name}...")
        col_summary = ", ".join([f"{c['column_name']} ({c['data_type']})" for c in columns])
        prompt = (
            f"Describe a database table named '{table_name}' with these columns: {col_summary}. "
            "Provide a concise, plain-English summary of what this table stores in a hospital setting. "
            "Do not return markdown formatting, just the text."
        )
        
        try:
            response = ollama.chat(
                model=LLM_MODEL,
                messages=[{'role': 'user', 'content': prompt}],
                options={'temperature': LLM_TEMPERATURE}
            )
            desc = response['message']['content'].strip()
            existing_descriptions[table_name] = desc
            updated = True
        except Exception as e:
            print(f"Error calling ollama for {table_name}: {e}")
            
    if updated:
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(existing_descriptions, f, indent=4)
        print(f"Saved generated descriptions to {OUTPUT_FILE} for human review.")
    else:
        print("No new tables to generate descriptions for.")

if __name__ == "__main__":
    generate_descriptions()
