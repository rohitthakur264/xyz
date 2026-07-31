import sys
import os
from schema_intel.generator import generate_descriptions
from schema_intel.embedder import embed_descriptions

def run_phase1():
    print("=== Phase 1: Schema Intelligence ===")
    
    # 1. Extraction & Generation (idempotent)
    print("\n[Step 1] Extracting schema and generating descriptions for new tables...")
    generate_descriptions()
    
    print("\n>>> PAUSE: At this point, you should open schema_intel/table_descriptions.json")
    print(">>> to sanity-check and edit any generated descriptions.")
    
    response = input("\nHave you reviewed table_descriptions.json? (y/N): ")
    if response.strip().lower() != 'y':
        print("Please review the descriptions before continuing.")
        sys.exit(0)
        
    # 2. Embedding
    print("\n[Step 2] Embedding reviewed descriptions into ChromaDB...")
    embed_descriptions()
    
    print("\n=== Phase 1 Complete ===")

if __name__ == "__main__":
    run_phase1()
