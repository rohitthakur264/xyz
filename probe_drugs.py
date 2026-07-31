from db.connection import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check fhir_drug_mst structure
print("=== fhir_drug_mst columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_drug_mst' ORDER BY ORDINAL_POSITION LIMIT 25")
print([r[0] for r in cursor.fetchall()])

print("\n=== fhir_drug_mst row count ===")
cursor.execute("SELECT COUNT(*) FROM fhir_drug_mst")
print(f"Rows: {cursor.fetchone()[0]}")

# prescription_dtl has itemid — check if that links to drug_mst
print("\n=== Does prescription_dtl.itemid link to fhir_drug_mst? ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_drug_mst' AND COLUMN_NAME IN ('id','drugid','itemid','drug_id')")
print("fhir_drug_mst key cols:", [r[0] for r in cursor.fetchall()])

# Try: prescription_dtl.itemid -> drug_mst.id
print("\n=== prescription_dtl joined with drug_mst via itemid ===")
try:
    cursor.execute("""
        SELECT pre.preid, pre.itemid, d.id, d.display, pre.dosage, pre.quantity
        FROM fhir_prescription_dtl pre
        JOIN fhir_drug_mst d ON pre.itemid = d.id
        LIMIT 5
    """)
    rows = cursor.fetchall()
    print(f"Rows: {len(rows)}")
    for r in rows: print(f"  {r}")
except Exception as e:
    print(f"Error: {e}")

# Try via drug_sale_dtl.drugid -> drug_mst.id
print("\n=== drug_sale_dtl.drugid -> drug_mst ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_drug_sale_dtl' AND COLUMN_NAME='drugid'")
has_drugid = len(cursor.fetchall()) > 0
print(f"fhir_drug_sale_dtl has drugid: {has_drugid}")

if has_drugid:
    cursor.execute("""
        SELECT dtl.drugsaleid, dtl.drugid, d.display, dtl.qty, dtl.rate
        FROM fhir_drug_sale_dtl dtl
        JOIN fhir_drug_mst d ON dtl.drugid = d.id
        LIMIT 5
    """)
    rows = cursor.fetchall()
    print(f"Rows: {len(rows)}")
    for r in rows: print(f"  {r}")

# Now: what does fhir_op_initial_assessment have? Does it store prescriptions?
print("\n=== fhir_op_initial_assessment columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_op_initial_assessment' ORDER BY ORDINAL_POSITION LIMIT 20")
print([r[0] for r in cursor.fetchall()])

print("\n=== fhir_op_initial_assessment for patient 180267 ===")
cursor.execute("SELECT COUNT(*) FROM fhir_op_initial_assessment WHERE patientid=180267")
print(f"Rows: {cursor.fetchone()[0]}")

# Check if prescription_dtl has an opasmt_id that links to op_initial_assessment
print("\n=== Prescription chain via op_initial_assessment ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_prescription_dtl' AND COLUMN_NAME IN ('opasmt_id','hm_id','visitid','visit_id')")
print("prescription_dtl link cols:", [r[0] for r in cursor.fetchall()])

# Try: op_initial_assessment -> prescription_dtl via opasmt_id / hm_id
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_prescription_dtl' AND COLUMN_NAME='hm_id'")
has_hm = len(cursor.fetchall()) > 0
if has_hm:
    cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_op_initial_assessment' AND COLUMN_NAME='hm_id'")
    oa_has_hm = len(cursor.fetchall()) > 0
    print(f"fhir_op_initial_assessment has hm_id: {oa_has_hm}")

# Full prescription chain for patient 180267 via op_initial_assessment
print("\n=== Full prescription chain for patient 180267 ===")
try:
    cursor.execute("""
        SELECT pre.preid, pre.itemid, pre.dosage, pre.quantity, pre.hm_id,
               d.display AS drug_name
        FROM fhir_op_initial_assessment oa
        JOIN fhir_prescription_dtl pre ON pre.hm_id = oa.id
        LEFT JOIN fhir_drug_mst d ON pre.itemid = d.id
        WHERE oa.patientid = 180267
        LIMIT 10
    """)
    rows = cursor.fetchall()
    print(f"via hm_id join: {len(rows)} rows")
    for r in rows: print(f"  {r}")
except Exception as e:
    print(f"hm_id join error: {e}")

conn.close()
print("\nDone.")
