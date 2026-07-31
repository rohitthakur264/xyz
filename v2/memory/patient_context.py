from dataclasses import dataclass, field
from typing import Optional
import time

@dataclass
class PatientContext:
    patient_id: str
    registration_no: str = ""
    name: str = ""
    age: str = ""
    gender: str = ""
    last_accessed: float = field(default_factory=time.time)
    
    def update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.last_accessed = time.time()
