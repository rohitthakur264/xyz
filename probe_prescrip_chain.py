from db.connection import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# op_initial_assessment PK is oppatint_id (not id!)
# Let's find how prescription_dtl.hm_id links to it
print("=== fhir_prescription_dtl.hm_id - what does it link to? ===")
cursor.execute("SELECT DISTINCT hm_id FROM fhir_prescription_dtl WHERE hm_id IS NOT NULL LIMIT 5")
sample_hmids = [r[0] for r in cursor.fetchall()]
print(f"Sample hm_ids: {sample_hmids}")

# Check if hm_id links to op_initial_assessment.oppatint_id
cursor.execute(f"SELECT oppatint_id, patientid, visitid FROM fhir_op_initial_assessment WHERE oppatint_id IN ({','.join(str(x) for x in sample_hmids[:3])}) LIMIT 5")
rows = cursor.fetchall()
print(f"hm_id->oppatint_id match: {rows}")

# What tables have oppatint_id?
print("\n=== Tables with oppatint_id ===")
cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND COLUMN_NAME='oppatint_id' GROUP BY TABLE_NAME")
print([r[0] for r in cursor.fetchall()])

# The real link: prescription_dtl for patient 180267 via op_initial_assessment.oppatint_id
print("\n=== Prescriptions for patient 180267 via op_initial_assessment ===")
cursor.execute("SELECT oppatint_id, patientid, visitid FROM fhir_op_initial_assessment WHERE patientid=180267")
oa_rows = cursor.fetchall()
print(f"op_initial_assessment rows: {oa_rows}")

if oa_rows:
    oppatint_ids = [r[0] for r in oa_rows]
    placeholders = ','.join(str(x) for x in oppatint_ids)
    cursor.execute(f"""
        SELECT pre.preid, pre.itemid, pre.dosage, pre.quantity, pre.hm_id,
               d.display AS drug_name
        FROM fhir_prescription_dtl pre
        LEFT JOIN fhir_drug_mst d ON pre.itemid = d.id
        WHERE pre.hm_id IN ({placeholders})
        LIMIT 20
    """)
    rows = cursor.fetchall()
    print(f"Prescription rows: {len(rows)}")
    for r in rows:
        print(f"  preid={r[0]}, itemid={r[1]}, dose={r[2]}, qty={r[3]}, drug='{r[5]}'")

# Also try direct preid approach - what is preid 495897 linked to?
print("\n=== What is preid 495897? ===")
cursor.execute("SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND COLUMN_NAME='preid' AND TABLE_NAME != 'fhir_prescription_dtl'")
print("Other tables with preid:", [f"{r[0]}.{r[1]}" for r in cursor.fetchall()])

# Try: does fhir_op_nurse_assessment_dtl link prescriptions?
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_op_nurse_assessment_dtl' AND COLUMN_NAME IN ('patientid','visitid','preid','hm_id') ORDER BY COLUMN_NAME")
print("fhir_op_nurse_assessment_dtl link cols:", [r[0] for r in cursor.fetchall()])

# Find the true prescription count for patient 180267 via all hm paths
print("\n=== Summary: prescription drugs for patient 180267 ===")
if oa_rows:
    cursor.execute(f"""
        SELECT COUNT(*) 
        FROM fhir_prescription_dtl pre
        WHERE pre.hm_id IN ({placeholders})
    """)
    print(f"Total prescription lines: {cursor.fetchone()[0]}")

conn.close()
print("\nDone.")
