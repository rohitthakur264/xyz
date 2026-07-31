from db.connection import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# First find the actual PK column name in fhir_visit_mst
print("=== fhir_visit_mst key columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_visit_mst' ORDER BY ORDINAL_POSITION LIMIT 15")
print([r[0] for r in cursor.fetchall()])

# fhir_prescription_dtl full column list
print("\n=== fhir_prescription_dtl ALL columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_prescription_dtl' ORDER BY ORDINAL_POSITION")
print([r[0] for r in cursor.fetchall()])

# What is the actual visit pk?
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_visit_mst' AND COLUMN_NAME IN ('visit_id','visitid','id')")
print("\nfhir_visit_mst PK candidates:", [r[0] for r in cursor.fetchall()])

# Check vitals
print("\n=== fhir_patient_vitals for patient 180267 ===")
cursor.execute("SELECT COUNT(*) FROM fhir_patient_vitals WHERE patientid=180267")
print(f"Rows: {cursor.fetchone()[0]}")

cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_patient_vitals' ORDER BY ORDINAL_POSITION LIMIT 15")
print("Columns:", [r[0] for r in cursor.fetchall()])

# Check allergies
print("\n=== fhir_patient_allergy for patient 180267 ===")
cursor.execute("SELECT COUNT(*) FROM fhir_patient_allergy WHERE patientid=180267")
print(f"Rows: {cursor.fetchone()[0]}")

# Check bill_mst
print("\n=== fhir_bill_mst columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_bill_mst' ORDER BY ORDINAL_POSITION LIMIT 20")
print([r[0] for r in cursor.fetchall()])

# Check OT tables
print("\n=== OT for patient 180267 ===")
cursor.execute("SELECT COUNT(*) FROM fhir_ot_scheduling_mst WHERE patientid=180267")
print(f"fhir_ot_scheduling_mst: {cursor.fetchone()[0]}")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_ot_scheduling_mst' ORDER BY ORDINAL_POSITION LIMIT 20")
print("Columns:", [r[0] for r in cursor.fetchall()])

# What is the actual patientid in fhir_patient_mst for registration 165881?
print("\n=== Confirm patient id for reg 165881 ===")
cursor.execute("SELECT id, registration_no, display FROM fhir_patient_mst WHERE registration_no='165881'")
rows = cursor.fetchall()
print(rows)

conn.close()
print("\nDone.")
