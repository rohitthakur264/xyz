import logging
import sys
import json
import os
from datetime import datetime
from config.settings import LOG_DIR, DEBUG_MODE

os.makedirs(LOG_DIR, exist_ok=True)

# Standard console formatter
console_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Setup root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)

# Console Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(console_formatter)
root_logger.addHandler(console_handler)

def get_logger(name: str):
    """Get a configured logger for a specific module."""
    return logging.getLogger(name)

class AuditLogger:
    """Specialized logger for recording complete interaction traces as JSON."""
    
    def __init__(self, log_file: str):
        self.log_file = log_file

    def log_interaction(self, session_id: str, doctor_id: str, patient_id: str, intent: str, 
                        question: str, sql: str, rows_returned: int, answer: str, 
                        execution_time_ms: float, retries: int, validation_errors: list):
        """Log a complete interaction trace."""
        record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "session_id": session_id,
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "intent": intent,
            "question": question,
            "generated_sql": sql,
            "rows_returned": rows_returned,
            "answer": answer,
            "execution_time_ms": execution_time_ms,
            "retries": retries,
            "validation_errors": validation_errors
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(record) + "\n")

audit_logger = AuditLogger(os.path.join(LOG_DIR, "audit_log.jsonl"))
