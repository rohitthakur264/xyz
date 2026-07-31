import os
import json

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

def _get_session_file(session_id):
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")

def load_session(session_id):
    """Loads a session's history, active patient, and last retrieved result context."""
    filepath = _get_session_file(session_id)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Migration for older list-based histories
            if isinstance(data, list):
                return {"active_patient": None, "last_result": None, "history": data}
            if "last_result" not in data:
                data["last_result"] = None
            if "active_patient" not in data:
                data["active_patient"] = None
            return data
    return {"active_patient": None, "last_result": None, "history": []}

def save_session(session_id, data):
    """Saves the session data."""
    filepath = _get_session_file(session_id)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, default=str)

def add_turn(session_id, question, answer, source="DRY_RUN"):
    """Appends a single Q&A turn to the session history."""
    session_data = load_session(session_id)
    session_data["history"].append({
        "q": question,
        "a": answer,
        "source": source
    })
    save_session(session_id, session_data)

def get_active_patient(session_id):
    return load_session(session_id).get("active_patient")

def set_active_patient(session_id, identifier):
    session_data = load_session(session_id)
    session_data["active_patient"] = identifier
    save_session(session_id, session_data)

def get_last_result(session_id):
    """Returns the last retrieved data result (SQL results/context) for multi-turn reasoning."""
    return load_session(session_id).get("last_result")

def set_last_result(session_id, result_data):
    """Saves the last retrieved data result context to the session."""
    session_data = load_session(session_id)
    session_data["last_result"] = result_data
    save_session(session_id, session_data)
