import json
import os

path = 'v2/database/extra_relationships.json'
with open(path, 'r') as f:
    rels = json.load(f)

for r in rels:
    # Fix referenced_column 'id' where it shouldn't be
    if r['referenced_table'] == 'fhir_patient_mst' and r['referenced_column'] == 'id':
        r['referenced_column'] = 'patientid'
    elif r['referenced_table'] == 'fhir_visit_mst' and r['referenced_column'] == 'id':
        r['referenced_column'] = 'visit_id'
    elif r['referenced_table'] == 'fhir_emp_mst' and r['referenced_column'] == 'id':
        r['referenced_column'] = 'empid'
        
    # Fix source column 'visit_id' -> 'visitid' for fhir_prescription_mst
    if r['table'] == 'fhir_prescription_mst' and r['column_name'] == 'visit_id':
        r['column_name'] = 'visitid'
        
    # Also fix fhir_visit_mst DocInCharge reference
    if r['table'] == 'fhir_visit_mst' and r['column_name'] == 'DocInCharge':
        r['column_name'] = 'docincharge'

with open(path, 'w') as f:
    json.dump(rels, f, indent=2)

print("Fixed extra_relationships.json")
