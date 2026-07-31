from db.connection import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# fhir_order_mst uses ordpatientid not patientid
print("=== fhir_order_mst for patient 180267 (ordpatientid) ===")
cursor.execute("SELECT ordid, ordpatientid, ordvisitid, orddatetime FROM fhir_order_mst WHERE ordpatientid=180267 LIMIT 5")
rows = cursor.fetchall()
print(f"Rows: {len(rows)}")
for r in rows: print(f"  {r}")

print("\n=== fhir_order_dtl columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_order_dtl' ORDER BY ORDINAL_POSITION LIMIT 20")
print([r[0] for r in cursor.fetchall()])

# Check drug_sale_mst visitid -> visit_mst.id validity
print("\n=== Drug sale visitid -> visit_mst.id match check ===")
cursor.execute("SELECT drugsaleid, visitid FROM fhir_drug_sale_mst WHERE visitid > 0 LIMIT 3")
for dsid, vid in cursor.fetchall():
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute(f"SELECT id, patientid FROM fhir_visit_mst WHERE id={vid}")
    match = c2.fetchone()
    print(f"  drug_sale visitid={vid} -> visit match: {match}")
    conn2.close()

# drug_sale_mst sample patientids are very low (0,50,72)
# fhir_patient_mst.id for our patient is 180267
# Check if drug_sale_mst uses a DIFFERENT patient id field
print("\n=== fhir_drug_sale_mst ALL columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_drug_sale_mst' ORDER BY ORDINAL_POSITION")
print([r[0] for r in cursor.fetchall()])

# Drug_mst - check if it's used for prescription via fhir_drug_sale_dtl.drugid -> drug_mst
# and drug_sale_mst.drugsaleid -> drug_sale_dtl
# Final chain confirmed: patient.id -> drug_sale_mst.patientid -> drug_sale_dtl -> drug_mst
# But our patient 180267 has 0 drug_sale rows. Let's confirm why:
print("\n=== Does fhir_patient_mst.id=180267 actually match fhir_drug_sale_mst.patientid field? ===")
cursor.execute("SELECT MIN(patientid), MAX(patientid), COUNT(DISTINCT patientid) FROM fhir_drug_sale_mst")
print(f"drug_sale_mst patientid range: {cursor.fetchone()}")

cursor.execute("SELECT MIN(id), MAX(id) FROM fhir_patient_mst")
print(f"patient_mst id range: {cursor.fetchone()}")

# If ranges don't overlap, drug_sale_mst uses a different ID (tmppatientid?)
print("\n=== fhir_drug_sale_mst tmppatientid check ===")
cursor.execute("SELECT drugsaleid, patientid, tmppatientid, visitid FROM fhir_drug_sale_mst LIMIT 5")
for r in cursor.fetchall(): print(f"  {r}")

# Check if tmppatientid links to fhir_patient_mst.id
cursor.execute("SELECT DISTINCT tmppatientid FROM fhir_drug_sale_mst WHERE tmppatientid IS NOT NULL AND tmppatientid > 0 LIMIT 5")
tmps = [r[0] for r in cursor.fetchall()]
print(f"Sample tmppatientids: {tmps}")
if tmps:
    cursor.execute(f"SELECT id, registration_no, display FROM fhir_patient_mst WHERE id IN ({','.join(str(x) for x in tmps)}) LIMIT 3")
    print(f"tmppatientid->patient_mst: {cursor.fetchall()}")

# NOW: the correct prescription query for patient 180267
# The real prescription approach: use fhir_drug_mst via fhir_prescription_dtl
# But we need to get prescription_dtl rows linked to patient 180267
# Let's try linking via fhir_tprbp_dtl which has patientid 
print("\n=== fhir_tprbp_dtl for patient 180267 ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_tprbp_dtl' ORDER BY ORDINAL_POSITION LIMIT 20")
print("columns:", [r[0] for r in cursor.fetchall()])
cursor.execute("SELECT * FROM fhir_tprbp_dtl WHERE patientid=180267 LIMIT 5")
rows = cursor.fetchall()
print(f"Rows: {len(rows)}")
for r in rows: print(f"  {r[:8]}")

conn.close()
print("\nDone.")
