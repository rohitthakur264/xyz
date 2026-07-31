# 🏥 Hospital AI Assistant (Production v2)

This repository contains the backend and frontend for an Orchestrator-driven, production-ready AI Assistant designed for EMR (Electronic Medical Records) queries. It translates natural language clinical questions into strict, validated MySQL queries.

## 🏗️ Architecture Overview

The system uses a **Chat Orchestrator** pattern instead of a monolithic linear prompt script. This ensures that every step is modular, strictly validated, and safe for a hospital environment.

### Core Pipeline (`v2/services/chat_orchestrator.py`)

1. **Session & Memory (`v2/memory/`)**:
   Maintains state across conversational turns using explicit, granular dataclasses (`DoctorContext`, `PatientContext`, `VisitContext`). Instead of passing massive unstructured chat logs to the LLM, the Orchestrator explicitly passes active patient IDs to scope the queries.

2. **Intent Detection (`v2/sql_pipeline/intent_detector.py`)**:
   Before writing any SQL, the LLM strictly classifies the question into domains like `PATIENT_SEARCH`, `BILLING`, `VITALS`, `PRESCRIPTION`.

3. **Query Planning & RAG (`v2/sql_pipeline/query_planner.py`)**:
   Based on the Intent, the Planner retrieves:
   - Only the specific tables needed (via ChromaDB embeddings).
   - Curated `few-shot` SQL examples for that specific intent.
   - It also queries the **Relationship Graph** (`NetworkX`) to mathematically determine the shortest join-paths (e.g. knowing it needs `fhir_visit_mst` to join `Patient` to `Billing`).

4. **SQL Generator & Corrector (`v2/sql_pipeline/sql_corrector.py`)**:
   - **Validator**: Strictly scans generated SQL for dangerous keywords (`DELETE`, `UPDATE`), ensures it starts with `SELECT`, and verifies the LLM didn't hallucinate tables outside the schema.
   - **Corrector**: If MySQL throws an `Unknown Column` error or the validator fails, the Pipeline automatically catches it, feeds the exact error back to the LLM, and regenerates the SQL. (Max 3 retries).

5. **Answer Generator (`v2/llm/answer_generator.py`)**:
   Takes the raw SQL rows and safely summarizes them for the doctor. To avoid context-overflow, it only operates on the first 20 rows.

## 🚀 Running the Application

### 1. Prerequisites
- `MySQL` running locally with the hospital database.
- `Ollama` running locally with `qwen2.5:14b` and `qwen2.5-coder:14b`.
- Python 3.10+

### 2. Install Dependencies
```bash
pip install fastapi uvicorn streamlit sentence-transformers chromadb mysql-connector-python networkx python-dotenv requests
```

### 3. Start the Backend API (FastAPI)
```bash
cd v2
python api/main.py
```
*The API will expose the Orchestrator at `http://localhost:8001/chat`*

### 4. Start the Frontend (Streamlit)
```bash
cd v2
streamlit run ui/app.py
```

## 🔒 Safety Measures Built-In
- All legacy columns (`old*`, `bak*`, `tmp*`) and tracking columns (`created_by`, `machine_name`) are stripped from the schema loader.
- SQL Execution is strictly capped via `LIMIT 50`.
- Destructive queries are hard-blocked by the Validator.
