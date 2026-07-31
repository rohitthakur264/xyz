from dataclasses import dataclass, field
from typing import Optional, List, Dict
import time

@dataclass
class DoctorContext:
    doctor_id: str
    name: str = ""
    specialty: str = ""
    department: str = ""
    preferences: dict = field(default_factory=dict)
    
    def update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
