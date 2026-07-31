import os
import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader

CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_data")
DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")

def get_chroma_client_and_collection():
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_or_create_collection(name="knowledge_collection")
    return collection

def delete_existing_chunks(collection, filename):
    """Deletes existing chunks from the collection for the given filename."""
    results = collection.get(where={"source_file": filename})
    if results and results['ids']:
        print(f"Deleting {len(results['ids'])} old chunks for {filename}...")
        collection.delete(ids=results['ids'])

def chunk_text(text, max_words=300, overlap=50):
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + max_words])
        chunks.append(chunk)
        i += max_words - overlap
    return chunks

def process_txt(filepath, filename, collection):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    pages = content.split("=== PAGE ")
    
    docs = []
    metadatas = []
    ids = []
    
    for p in pages:
        if not p.strip(): continue
        lines = p.split("===\n", 1)
        if len(lines) == 2:
            page_num_str = lines[0].strip()
            page_text = lines[1].strip()
            try:
                page_num = int(page_num_str)
            except ValueError:
                page_num = 1
        else:
            page_num = 1
            page_text = p.strip()
            
        chunks = chunk_text(page_text)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{filename}_p{page_num}_c{i}"
            docs.append(chunk)
            metadatas.append({"source_file": filename, "page_number": page_num})
            ids.append(chunk_id)
            
    if docs:
        from sentence_transformers import SentenceTransformer
        embedder = SentenceTransformer('all-MiniLM-L6-v2')
        embeddings = embedder.encode(docs).tolist()
        collection.add(documents=docs, embeddings=embeddings, metadatas=metadatas, ids=ids)
        print(f"Added {len(docs)} chunks for {filename}.")

def process_pdf(filepath, filename, collection):
    reader = PdfReader(filepath)
    docs = []
    metadatas = []
    ids = []
    
    for i, page in enumerate(reader.pages):
        page_num = i + 1
        text = page.extract_text()
        if not text:
            continue
            
        chunks = chunk_text(text)
        for j, chunk in enumerate(chunks):
            chunk_id = f"{filename}_p{page_num}_c{j}"
            docs.append(chunk)
            metadatas.append({"source_file": filename, "page_number": page_num})
            ids.append(chunk_id)
            
    if docs:
        from sentence_transformers import SentenceTransformer
        embedder = SentenceTransformer('all-MiniLM-L6-v2')
        embeddings = embedder.encode(docs).tolist()
        collection.add(documents=docs, embeddings=embeddings, metadatas=metadatas, ids=ids)
        print(f"Added {len(docs)} chunks for {filename}.")

def ingest_documents():
    print("=== Phase 3: Document Ingestion ===")
    if not os.path.exists(DOCS_DIR):
        print(f"Docs directory not found: {DOCS_DIR}")
        return
        
    collection = get_chroma_client_and_collection()
    
    for filename in os.listdir(DOCS_DIR):
        filepath = os.path.join(DOCS_DIR, filename)
        if os.path.isfile(filepath):
            print(f"Processing {filename}...")
            delete_existing_chunks(collection, filename)
            
            if filename.lower().endswith('.txt'):
                process_txt(filepath, filename, collection)
            elif filename.lower().endswith('.pdf'):
                process_pdf(filepath, filename, collection)
            else:
                print(f"Skipping unsupported file type: {filename}")

if __name__ == "__main__":
    ingest_documents()
