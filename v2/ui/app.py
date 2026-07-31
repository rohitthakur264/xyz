import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import requests
from config.settings import LOG_LEVEL
from config.logging import get_logger

logger = get_logger(__name__)

API_URL = "http://127.0.0.1:8001/chat"

st.set_page_config(page_title="Hospital AI Assistant", page_icon="🏥", layout="wide")

st.title("🏥 Hospital AI Assistant (v2)")
st.markdown("A production-ready EMR Assistant using Agentic AI.")

# Initialize session state for memory
if "session_id" not in st.session_state:
    st.session_state.session_id = "demo_session_1"
if "doctor_id" not in st.session_state:
    st.session_state.doctor_id = "doc_test_1"
if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar for config
with st.sidebar:
    st.header("Session Info")
    st.text(f"Session: {st.session_state.session_id}")
    st.text(f"Doctor: {st.session_state.doctor_id}")
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

# Render chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("metadata"):
            with st.expander("View Debug Details"):
                st.json(message["metadata"])

# Chat input
if prompt := st.chat_input("Ask about a patient, visit, or billing..."):
    # 1. Append user prompt to state
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 2. Perform API request under spinner
    with st.spinner("Analyzing request..."):
        try:
            response = requests.post(API_URL, json={
                "session_id": st.session_state.session_id,
                "doctor_id": st.session_state.doctor_id,
                "question": prompt
            }, timeout=300)
            response.raise_for_status()
            data = response.json()
            
            answer = data["answer"]
            metadata = {
                "intent": data.get("intent", "UNKNOWN"),
                "tables_used": data.get("tables", []),
                "sql_executed": data.get("sql", "")
            }
            
            st.session_state.messages.append({
                "role": "assistant", 
                "content": answer,
                "metadata": metadata
            })
        except requests.exceptions.ConnectionError:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Error: Backend API is not running. Please start FastAPI on port 8001.",
                "metadata": None
            })
        except requests.exceptions.RequestException as e:
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"API Error: {e}",
                "metadata": None
            })

    # 3. Trigger clean rerun for deterministic React DOM rendering
    st.rerun()
