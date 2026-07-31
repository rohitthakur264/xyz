from db.connection import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# fhir_visit_mst uses 'id' as PK (not visit_id, not visitid)
# fhir_patient_vitals uses 'visit_id' (linking to fhir_visit_mst.id)
# fhir_bill_mst uses 'visit_id' (linking to fhir_visit_mst.id) and also has 'registration_no'

print("=== Bill records for patient 165881 via registration_no ===")
cursor.execute("SELECT billno, visit_id, netamount, billdate FROM fhir_bill_mst WHERE registration_no='165881' LIMIT 5")
rows = cursor.fetchall()
print(f"Rows: {len(rows)}")
for r in rows: print(f"  {r}")

print("\n=== Bill records via patientid->visit join ===")
cursor.execute("""
    SELECT b.billno, b.visit_id, b.netamount, b.billdate
    FROM fhir_bill_mst b
    JOIN fhir_visit_mst v ON b.visit_id = v.id
    WHERE v.patientid = 180267
    LIMIT 5
""")
rows = cursor.fetchall()
print(f"Rows: {len(rows)}")
for r in rows: print(f"  {r}")

print("\n=== Vitals for patient 180267 via visit ===")
cursor.execute("""
    SELECT pv.id, pv.visit_id, pv.pulse, pv.temperature, pv.systolic, pv.diastolic, pv.reading_datetime
    FROM fhir_patient_vitals pv
    WHERE pv.patientid = 180267
    LIMIT 5
""")
rows = cursor.fetchall()
print(f"Rows: {len(rows)}")
for r in rows: print(f"  {r}")

print("\n=== OT details for patient 180267 ===")
cursor.execute("""
    SELECT scheduleid, visitid, patientid, operationid, operationdate, cheifsurgeonid
    FROM fhir_ot_scheduling_mst
    WHERE patientid = 180267
    LIMIT 5
""")
rows = cursor.fetchall()
print(f"Rows: {len(rows)}")
for r in rows: print(f"  {r}")

# Check fhir_ot_scheduling_mst has operationid that links to what?
print("\n=== Tables with operation/procedure names ===")
cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND COLUMN_NAME IN ('operationname','procedurename','operation_name') GROUP BY TABLE_NAME")
print([r[0] for r in cursor.fetchall()])

# Check drug sale for patient via visit
print("\n=== Drug sales via visit join ===")
cursor.execute("""
    SELECT ds.drugsaleid, ds.patientid, ds.visitid, ds.saledate
    FROM fhir_drug_sale_mst ds
    JOIN fhir_visit_mst v ON ds.visitid = v.id
    WHERE v.patientid = 180267
    LIMIT 5
""")
rows = cursor.fetchall()
print(f"Rows: {len(rows)}")
for r in rows: print(f"  {r}")

# Also try direct
cursor.execute("SELECT drugsaleid, patientid, visitid, saledate FROM fhir_drug_sale_mst WHERE visitid IN (SELECT id FROM fhir_visit_mst WHERE patientid=180267) LIMIT 5")
rows = cursor.fetchall()
print(f"Drug sales via subquery: {len(rows)} rows")

# Check prescription_dtl - what is preid?
print("\n=== What does preid in prescription_dtl link to? ===")
cursor.execute("SELECT DISTINCT preid FROM fhir_prescription_dtl LIMIT 5")
sample_preids = [r[0] for r in cursor.fetchall()]
print(f"Sample preids: {sample_preids}")
# Check if preid matches anything in visit
cursor.execute(f"SELECT id FROM fhir_visit_mst WHERE id IN ({','.join(str(p) for p in sample_preids[:3])}) LIMIT 5")
rows = cursor.fetchall()
print(f"preid->visit match: {rows}")
# Check op_initial_assessment
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_op_initial_assessment' AND COLUMN_NAME IN ('preid','prescriptionid','id','opasmt_id','patientid','visitid')")
print("fhir_op_initial_assessment:", [r[0] for r in cursor.fetchall()])

conn.close()
print("\nDone.")
