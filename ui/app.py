import streamlit as st
import requests
import uuid

API_URL = "http://localhost:8000/chat"

st.set_page_config(page_title="Hospital AI Assistant", page_icon="🏥", layout="centered")

st.title("🏥 Hospital AI Assistant")
st.markdown("Ask a question about the hospital database or medical knowledge base.")

# Initialize session state for session ID
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "debug" in message and message["debug"]:
            with st.expander("Debug Information"):
                st.json(message["debug"])

# Accept user input
if prompt := st.chat_input("E.g. What is the postcare protocol for appendectomy?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(prompt)

    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("*(Thinking...)*")
        
        try:
            response = requests.post(
                API_URL,
                json={"question": prompt, "session_id": st.session_state.session_id},
                timeout=300
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract fields
            answer = data.get("answer", "No answer provided.")
            rewritten_question = data.get("rewritten_question", prompt)
            source_used = data.get("source_used", "unknown")
            route_decision = data.get("route_decision", "unknown")
            
            # Build the display markdown
            display_text = f"**Interpreted as:** {rewritten_question}\n\n"
            display_text += f"---\n\n{answer}\n\n"
            display_text += f"`[Source: {source_used}]` `[Route: {route_decision}]`"
            
            message_placeholder.markdown(display_text)
            
            debug_info = data.get("debug")
            if debug_info:
                with st.expander("Debug Information"):
                    st.json(debug_info)
            
            # Save assistant response to chat history
            st.session_state.messages.append({"role": "assistant", "content": display_text, "debug": debug_info})
            
        except requests.exceptions.RequestException as e:
            error_msg = f"**Error connecting to the backend API:**\n{e}"
            message_placeholder.markdown(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
