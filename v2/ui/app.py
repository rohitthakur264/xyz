import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import requests
from config.settings import LOG_LEVEL
from config.logging import get_logger

logger = get_logger(__name__)

API_URL = "http://127.0.0.1:8001/chat"
BASE_URL = API_URL.replace('/chat', '')

st.set_page_config(page_title="Hospital AI Assistant", page_icon="🏥", layout="wide")

import uuid

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "doctor_id" not in st.session_state:
    st.session_state.doctor_id = None

# ---------------------------------------------------------------- #
# Login gate — nothing else renders until this passes. A doctor picks
# their name (friendly UX) AND enters their access key (the real
# credential); we verify the key actually resolves to the SELECTED name
# via /whoami before letting them in. Picking a name alone would let
# anyone attribute writes to any doctor with zero authentication — the
# key is still required and checked server-side, config-driven via
# API_KEYS_MAP in .env, never hardcoded here.
# ---------------------------------------------------------------- #
if not st.session_state.logged_in:
    st.title("🏥 Hospital AI Assistant — Login")

    try:
        doctors_resp = requests.get(f"{BASE_URL}/doctors", timeout=5)
        doctor_names = doctors_resp.json().get("doctors", []) if doctors_resp.status_code == 200 else []
    except Exception:
        doctor_names = []

    with st.form("login_form"):
        if doctor_names:
            selected_doctor = st.selectbox("Select your name", options=doctor_names)
        else:
            selected_doctor = st.text_input("Your doctor ID")
            st.caption("⚠️ Couldn't reach the backend to load the doctor list — enter your ID manually.")

        entered_key = st.text_input("Access Key", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            if not entered_key:
                st.error("Please enter your access key.")
            else:
                try:
                    resp = requests.get(f"{BASE_URL}/whoami", headers={"X-API-Key": entered_key}, timeout=5)
                    if resp.status_code != 200:
                        st.error("Invalid access key.")
                    elif resp.json().get("doctor_id") != selected_doctor:
                        st.error("This key doesn't match the selected doctor. Check your key or selection.")
                    else:
                        st.session_state.logged_in = True
                        st.session_state.api_key = entered_key
                        st.session_state.doctor_id = selected_doctor
                        st.rerun()
                except Exception as e:
                    st.error(f"Couldn't reach the backend: {e}")

    st.stop()  # Hard stop — nothing below this renders until logged in.

st.title("🏥 Hospital AI Assistant (v2)")
st.markdown("A production-ready EMR Assistant using Agentic AI.")

# Initialize session state for memory
if "session_id" not in st.session_state:
    st.session_state.session_id = f"session_{uuid.uuid4().hex[:8]}"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "active_patient" not in st.session_state:
    st.session_state.active_patient = None

# Sidebar for config
with st.sidebar:
    st.header("Session Info")
    st.caption(f"👩⚕️ Logged in as: **{st.session_state.doctor_id}**")
    if st.button("🚪 Log out"):
        st.session_state.logged_in = False
        st.session_state.api_key = ""
        st.session_state.doctor_id = None
        st.rerun()
    st.text(f"Session: {st.session_state.session_id}")

    if st.button("Clear Chat"):
        import uuid
        st.session_state.session_id = f"session_{uuid.uuid4().hex[:8]}"
        st.session_state.messages = []
        st.session_state.active_patient = None
        st.rerun()

    if st.session_state.active_patient:
        st.markdown("---")
        st.header("Actions")
        
        if st.button("👁️ Preview Medical Record", use_container_width=True):
            with st.spinner("Fetching full medical record..."):
                preview_url = f"{API_URL.replace('/chat', '')}/export/preview/session/{st.session_state.session_id}"
                try:
                    resp = requests.get(preview_url, headers={"X-API-Key": st.session_state.api_key})
                    if resp.status_code == 200:
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": resp.json().get("markdown", ""),
                            "is_medical_record": True
                        })
                        st.rerun()
                    else:
                        st.error("Could not fetch preview.")
                except Exception as e:
                    st.error(f"Connection error: {e}")

        # ---------------------------------------------------------- #
        # Add Record (prescription / lab test / vitals / ...)
        # Form fields are rendered from the backend's insert_schema.json
        # via /records/form/{entity_type} -- NOT hardcoded here, so a new
        # field/entity added in config shows up without a UI code change.
        # ---------------------------------------------------------- #
        st.markdown("---")
        st.header("➕ Add Record")

        base_url = API_URL.replace('/chat', '')
        headers = {"X-API-Key": st.session_state.api_key}

        try:
            entities_resp = requests.get(f"{base_url}/records/entities", headers=headers, timeout=10)
            entities = entities_resp.json().get("entities", {}) if entities_resp.status_code == 200 else {}
        except Exception:
            entities = {}

        if not entities:
            st.caption("Add-record is unavailable (disabled, or backend unreachable).")
        else:
            entity_key = st.selectbox(
                "Record type", options=list(entities.keys()),
                format_func=lambda k: entities[k], key="add_record_entity",
            )

            try:
                form_resp = requests.get(f"{base_url}/records/form/{entity_key}", headers=headers, timeout=10)
                form_schema = form_resp.json().get("schema", {}) if form_resp.status_code == 200 else {}
            except Exception:
                form_schema = {}

            if form_schema:
                with st.form(key=f"add_record_form_{entity_key}"):
                    field_values = {}
                    for field in form_schema.get("fields", []):
                        fkey, flabel, ftype = field["key"], field["label"], field.get("type", "text")
                        required_mark = " *" if field.get("required") else ""

                        if ftype == "number":
                            field_values[fkey] = st.number_input(
                                flabel + required_mark,
                                min_value=float(field.get("min", 0)),
                                max_value=float(field.get("max", 1000)),
                                key=f"{entity_key}_{fkey}",
                            )
                        elif ftype == "datetime":
                            d = st.date_input(flabel + required_mark + " (date)", key=f"{entity_key}_{fkey}_d")
                            t = st.time_input(flabel + required_mark + " (time)", key=f"{entity_key}_{fkey}_t")
                            field_values[fkey] = f"{d}T{t}"
                        elif ftype == "lookup":
                            field_values[fkey] = st.text_input(flabel + required_mark, key=f"{entity_key}_{fkey}")
                        else:
                            field_values[fkey] = st.text_input(flabel + required_mark, key=f"{entity_key}_{fkey}")

                    submitted = st.form_submit_button("Save Record", use_container_width=True)
                    if submitted:
                        try:
                            resp = requests.post(
                                f"{base_url}/records/insert",
                                json={
                                    "session_id": st.session_state.session_id,
                                    "entity_type": entity_key,
                                    "field_values": field_values,
                                },
                                headers=headers,
                                timeout=30,
                            )
                            if resp.status_code == 200:
                                st.success(f"{entities[entity_key]} saved successfully.")
                            else:
                                st.error(resp.json().get("detail", "Could not save record."))
                        except Exception as e:
                            st.error(f"Connection error: {e}")

# Display active patient banner
if st.session_state.active_patient:
    patient = st.session_state.active_patient
    st.info(f"👤 **Active Patient:** {patient.get('name', 'Unknown')} (Reg No: `{patient.get('reg_no', 'N/A')}`)")



# Render chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=True)
        
        # Render graph if available
        if message.get("intent") == "VITALS" and message.get("raw_data"):
            try:
                df = pd.DataFrame(message["raw_data"])
                if not df.empty:
                    # Sort chronologically by the first date/time column found
                    date_cols = [c for c in df.columns if "date" in c.lower() or "time" in c.lower()]
                    if date_cols:
                        df[date_cols[0]] = pd.to_datetime(df[date_cols[0]], errors='coerce')
                        df = df.sort_values(by=date_cols[0], ascending=True)
                        df = df.set_index(date_cols[0])
                    
                    # Split BP string (e.g. "120/80") into numeric Systolic/Diastolic
                    bp_col = next((c for c in df.columns if "bp" in c.lower() or "blood" in c.lower()), None)
                    if bp_col and df[bp_col].dtype == object:
                        split_bp = df[bp_col].astype(str).str.split('/', n=1, expand=True)
                        if split_bp.shape[1] == 2:
                            df['Systolic BP'] = pd.to_numeric(split_bp[0], errors='coerce')
                            df['Diastolic BP'] = pd.to_numeric(split_bp[1], errors='coerce')
                        df = df.drop(columns=[bp_col])
                    
                    # Select only numeric columns for charting
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    if not numeric_cols.empty:
                        import altair as alt
                        
                        df_chart = df.reset_index()
                        time_col = date_cols[0] if date_cols else df_chart.columns[0]
                        
                        st.markdown("### 📈 Patient Vitals Trends")

                        # Combine every vital into ONE chart by normalizing each
                        # vital to a 0-100 scale, where 0 = low end of the normal
                        # range and 100 = high end of the normal range. This way
                        # BP (mmHg), Temp (°C), Pulse (bpm) and Respiratory (/min)
                        # are all comparable on a single shared y-axis, while the
                        # tooltip still shows the true, original value.
                        bp_cols = [c for c in numeric_cols if 'systolic' in c.lower() or 'diastolic' in c.lower()]
                        temp_col = next((c for c in numeric_cols if 'temp' in c.lower()), None)
                        pulse_col = next((c for c in numeric_cols if 'pulse' in c.lower() or 'heart' in c.lower()), None)
                        resp_col = next((c for c in numeric_cols if 'resp' in c.lower()), None)

                        # (column, display name, low bound, high bound, color)
                        vital_specs = []
                        for c in bp_cols:
                            if 'sys' in c.lower():
                                vital_specs.append((c, 'Systolic BP', 90, 120, '#1f77ff'))
                            else:
                                vital_specs.append((c, 'Diastolic BP', 60, 80, '#2ca02c'))
                        if temp_col:
                            vital_specs.append((temp_col, 'Temperature', 36.1, 37.2, '#ff7f0e'))
                        if pulse_col:
                            vital_specs.append((pulse_col, 'Pulse', 60, 100, '#9467bd'))
                        if resp_col:
                            vital_specs.append((resp_col, 'Respiratory Rate', 12, 20, '#17a2a2'))

                        if vital_specs:
                            long_rows = []
                            for c, label, lo, hi, color in vital_specs:
                                for _, row in df_chart.iterrows():
                                    val = row[c]
                                    if pd.isna(val):
                                        continue
                                    long_rows.append({
                                        time_col: row[time_col],
                                        'Vital': label,
                                        'Value': val,
                                        'Low': lo,
                                        'High': hi,
                                        'Range': f"{lo}-{hi}",
                                    })
                            df_long = pd.DataFrame(long_rows)

                            color_map = {label: color for _, label, _, _, color in vital_specs}
                            order = [label for _, label, _, _, _ in vital_specs]

                            # One row per vital, each with its OWN y-scale (so an
                            # extreme reading in one vital - e.g. a 43C fever -
                            # can't squash the others into an unreadable flat
                            # line the way a single shared/normalized axis does).
                            # All rows share the same x-axis (time) so trends
                            # still line up visually, and it renders as a single
                            # chart the user scrolls through together.
                            charts = []
                            for label in order:
                                sub = df_long[df_long['Vital'] == label]
                                lo = float(sub['Low'].iloc[0])
                                hi = float(sub['High'].iloc[0])
                                color = str(color_map[label])

                                band = alt.Chart(pd.DataFrame({'y1': [lo], 'y2': [hi]})).mark_rect(
                                    color='lightgreen', opacity=0.2
                                ).encode(y=alt.Y('y1:Q', title=label), y2='y2:Q')

                                base = alt.Chart(sub).encode(
                                    x=alt.X(f'{time_col}:T', title='Time' if label == order[-1] else None,
                                            axis=alt.Axis(labels=(label == order[-1]))),
                                    y=alt.Y('Value:Q', title=label, scale=alt.Scale(zero=False)),
                                    tooltip=[time_col, 'Vital', 'Value', 'Range'],
                                )
                                line = base.mark_line(color=color)
                                # Highlight out-of-range points in red regardless of the vital's own color
                                points = base.mark_circle(size=65).encode(
                                    color=alt.condition(
                                        (alt.datum.Value < lo) | (alt.datum.Value > hi),
                                        alt.value('red'),
                                        alt.value(color),
                                    )
                                )
                                row_chart = alt.layer(band, line, points).properties(height=110)
                                charts.append(row_chart)

                            combined = alt.vconcat(*charts).resolve_scale(y='independent').properties(
                                title='Patient Vitals Trends (green band = normal range, red dot = out of range)'
                            )
                            st.altair_chart(combined, use_container_width=True)
                            st.caption("Each vital keeps its own scale so a severe reading in one vital doesn't flatten the others. Hover a point for the exact value.")
            except Exception as e:
                st.error(f"Could not render graph: {e}")

        if message.get("metadata"):
            with st.expander("View Debug Details"):
                st.json(message["metadata"])

        # ---------------------------------------------------------- #
        # Inline "Review & Edit" form for ADD_RECORD (add prescription/
        # lab test/vitals via chat). Only shown for the LATEST message
        # (so confirming/cancelling an old one doesn't leave stale forms
        # around), and only while nothing has been confirmed/cancelled
        # yet for it. All values are editable before Confirm — clicking
        # Confirm submits directly to /records/insert (full validation
        # runs again there), completely bypassing the need to retype
        # anything in chat.
        # ---------------------------------------------------------- #
        is_last_message = message is st.session_state.messages[-1]
        if message.get("add_record_form") and is_last_message and not st.session_state.get("add_record_resolved"):
            form_data = message["add_record_form"]
            base_url = API_URL.replace('/chat', '')
            headers = {"X-API-Key": st.session_state.api_key}

            with st.form(key="inline_add_record_form"):
                st.caption(f"📋 {form_data['visit_label']}  •  👤 {form_data['patient_label']}")
                edited_values = {}
                for field in form_data["fields"]:
                    fkey, flabel, ftype = field["key"], field["label"], field["type"]
                    required_mark = " *" if field.get("required") else ""

                    if ftype == "number":
                        edited_values[fkey] = st.number_input(
                            flabel + required_mark,
                            min_value=float(field.get("min", 0) or 0),
                            max_value=float(field.get("max", 1000) or 1000),
                            value=float(field["value"]) if field.get("value") not in (None, "") else float(field.get("min", 0) or 0),
                            key=f"add_rec_{fkey}",
                        )
                    elif ftype == "lookup":
                        options = field.get("options", [])
                        option_map = {o["label"]: o["id"] for o in options}
                        current_id = field.get("value")
                        current_label = next((o["label"] for o in options if o["id"] == current_id), None)
                        labels = list(option_map.keys())
                        default_idx = labels.index(current_label) if current_label in labels else 0
                        if labels:
                            if len(labels) == 1:
                                st.text_input(flabel + required_mark, value=labels[0], key=f"add_rec_{fkey}_ro", disabled=True)
                                edited_values[fkey] = option_map[labels[0]]
                            else:
                                choice = st.selectbox(flabel + required_mark, options=labels, index=default_idx, key=f"add_rec_{fkey}")
                                edited_values[fkey] = option_map[choice]
                        else:
                            st.caption(f"No matches found for {flabel} — please check spelling.")
                            edited_values[fkey] = None
                    elif ftype == "datetime":
                        st.text_input(flabel + required_mark, value=str(field.get("value") or ""), key=f"add_rec_{fkey}", disabled=True)
                        edited_values[fkey] = field.get("value")
                    else:
                        edited_values[fkey] = st.text_input(flabel + required_mark, value=str(field.get("value") or ""), key=f"add_rec_{fkey}")

                col_a, col_b = st.columns(2)
                with col_a:
                    confirm_clicked = st.form_submit_button("✅ Confirm", use_container_width=True)
                with col_b:
                    cancel_clicked = st.form_submit_button("❌ Cancel", use_container_width=True)

                if confirm_clicked:
                    try:
                        resp = requests.post(
                            f"{base_url}/records/insert",
                            json={
                                "session_id": st.session_state.session_id,
                                "entity_type": form_data["entity_type"],
                                "field_values": edited_values,
                            },
                            headers=headers, timeout=30,
                        )
                        if resp.status_code == 200:
                            st.session_state.add_record_resolved = True
                            st.session_state.messages.append({"role": "assistant", "content": f"✅ Saved successfully."})
                        else:
                            st.session_state.messages.append({"role": "assistant", "content": f"❌ {resp.json().get('detail', 'Could not save.')}"})
                    except Exception as e:
                        st.session_state.messages.append({"role": "assistant", "content": f"Connection error: {e}"})
                    st.rerun()

                if cancel_clicked:
                    # Notify backend to clear the pending state
                    try:
                        requests.post(
                            f"{API_URL}/chat",
                            json={"message": "cancel", "session_id": session_id, "doctor_info": doctor_info}
                        )
                    except Exception:
                        pass
                    st.session_state.add_record_resolved = True
                    st.session_state.messages.append({"role": "assistant", "content": "Cancelled. Nothing was saved."})
                    st.rerun()

        if message.get("is_medical_record"):
            col1, col2, col3 = st.columns([2, 2, 4])
            with col1:
                export_url = f"{API_URL.replace('/chat', '')}/export/session/{st.session_state.session_id}/full-record?api_key_query={st.session_state.api_key}"
                st.markdown(f'<a href="{export_url}" target="_blank" style="text-decoration:none; padding:8px 12px; background-color:#4CAF50; color:white; border-radius:4px; display:inline-block; margin-top: 10px; width:100%; text-align:center;">⬇️ Complete Record</a>', unsafe_allow_html=True)
            with col2:
                if st.button("❌ Close Report", use_container_width=True, key=f"close_report_{message.get('intent', 'report')}"):
                    st.session_state.messages = [m for m in st.session_state.messages if not m.get("is_medical_record")]
                    st.rerun()


# Chat input
if prompt := st.chat_input("Ask about a patient, visit, or billing..."):
    # 1. Append user prompt to state
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # 1.5. Render user message immediately
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Perform API request under spinner
    with st.spinner("Analyzing request..."):
        try:
            response = requests.post(API_URL, json={
                "session_id": st.session_state.session_id,
                "question": prompt
            }, headers={"X-API-Key": st.session_state.api_key}, timeout=300)
            response.raise_for_status()
            data = response.json()
            
            # Update active patient if returned
            if data.get("patient"):
                st.session_state.active_patient = data["patient"]
            
            answer = data["answer"]
            metadata = {
                "intent": data.get("intent", "UNKNOWN"),
                "tables_used": data.get("tables", []),
                "sql_executed": data.get("sql", "")
            }
            
            raw_data = data.get("raw_data")
            
            st.session_state.messages.append({
                "role": "assistant", 
                "content": answer,
                "metadata": metadata,
                "raw_data": raw_data,
                "intent": metadata["intent"],
                "add_record_form": data.get("add_record_form"),
            })
            if data.get("add_record_form"):
                st.session_state.add_record_resolved = False
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
