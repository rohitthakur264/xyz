import os
os.environ['USE_SCHEMA_CACHE'] = 'False'
from dotenv import load_dotenv
load_dotenv('.env')
from database.schema_loader import SchemaLoader
s = SchemaLoader().load_schema()
for t in ['fhir_rad_imgresult', 'fhir_rad_services', 'fhir_rad_testtemplate']:
    print(f'--- {t} ---')
    info = s.get(t, {})
    cols = info.get('columns', [])
    for c in cols:
        print(f"{c['column_name']} - {c['data_type']}")
    print("FKs:", info.get('foreign_keys', []))
