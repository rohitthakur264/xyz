import sys
from knowledge_pipeline.retriever import retrieve_chunks
from knowledge_pipeline.relevance_checker import filter_relevant_chunks
from knowledge_pipeline.answerer import generate_answer
from config.settings import RAG_RETRIEVAL_K, RAG_DISTANCE_THRESHOLD

def execute_rag_pipeline(question: str) -> dict:
    """Runs the RAG pipeline and returns a dictionary with the results."""
    # Step 1: Retrieve chunks
    candidate_chunks = retrieve_chunks(question, k=RAG_RETRIEVAL_K, distance_threshold=RAG_DISTANCE_THRESHOLD)
    
    # Step 2: Relevance check
    verified_chunks = filter_relevant_chunks(question, candidate_chunks)
    
    # Step 3: Generate answer
    final_answer = generate_answer(question, verified_chunks)
    
    return {
        "answer": final_answer,
        "verified_chunks": verified_chunks,
        "candidate_count": len(candidate_chunks),
        "debug_info": {
            "candidate_count": len(candidate_chunks),
            "verified_count": len(verified_chunks),
            "chunks": [
                {
                    "source": c['metadata'].get('source', 'unknown'),
                    "distance": c.get('distance'),
                    "passed_relevance": c in verified_chunks
                } for c in candidate_chunks
            ]
        }
    }

def run_phase3():
    print("=== Phase 3: Knowledge Base RAG Pipeline ===")
    
    question = input("\nEnter a knowledge-based question (e.g., 'What is the postcare for appendectomy?'): ")
    if not question.strip():
        print("Empty question. Exiting.")
        sys.exit(0)
        
    print("\n[Step 1] Retrieving chunks from ChromaDB...")
    result = execute_rag_pipeline(question)
    print(f"Retrieved {result['candidate_count']} candidate chunks (passed similarity floor).")
    
    print("\n[Step 2] Running strict relevance check on candidates...")
    print(f"Passed relevance check: {len(result['verified_chunks'])} chunks.")
    
    print("\n[Step 3] Generating final answer...")
    print("\n=== Final Answer ===")
    print(result["answer"])
    print("====================")

if __name__ == "__main__":
    run_phase3()
