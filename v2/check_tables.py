import json
from database.schema_anchors import PATIENT_FK_CANDIDATES

with open('schema_intel/schema_cache.json', 'r') as f:
    data = json.load(f)

def print_table_info(t_name):
    if t_name not in data:
        print(f"Table {t_name} not found")
        return
    cols = [c['column_name'] for c in data[t_name].get('columns', [])]
    print(f"Table: {t_name}")
    print(f"  Columns: {', '.join(cols[:15])}{'...' if len(cols)>15 else ''}")

print_table_info('fhir_prescription_mst')
print_table_info('fhir_prescription_dtl')
print_table_info('fhir_lab_test_result')
print_table_info('fhir_ot_scheduling_mst')
print_table_info('fhir_allergies_mst')
print_table_info('fhir_tprbp_dtl')
