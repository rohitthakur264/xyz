from dataclasses import dataclass, field
from typing import Optional
import time

@dataclass
class VisitContext:
    visit_id: str
    patient_id: str
    admission_no: str = ""
    visit_type: str = ""  # IPD/OPD
    department: str = ""
    visit_no: str = ""
    visit_date: str = ""
    last_accessed: float = field(default_factory=time.time)
    
    def display_label(self) -> str:
        if self.visit_no:
            return f"{self.visit_no} ({self.visit_type})"
        return f"Visit {self.visit_id}"
    
    def update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.last_accessed = time.time()
