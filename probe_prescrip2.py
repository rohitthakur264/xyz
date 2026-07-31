from db.connection import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# hm_id is always 0 - not used for linking. preid 495897 has no parent table.
# Let's find what preid actually IS by querying what unique preids exist and seeing
# if any column in any table references them

print("=== What preids exist? Range check ===")
cursor.execute("SELECT MIN(preid), MAX(preid), COUNT(DISTINCT preid) FROM fhir_prescription_dtl")
print(cursor.fetchone())

# patient 180267 has visits 576473 and 579019
# Is there a table that has both visitid and preid?
print("\n=== Tables that have BOTH visitid AND preid columns ===")
cursor.execute("""
    SELECT c1.TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS c1
    JOIN INFORMATION_SCHEMA.COLUMNS c2 ON c1.TABLE_NAME=c2.TABLE_NAME AND c1.TABLE_SCHEMA=c2.TABLE_SCHEMA
    WHERE c1.TABLE_SCHEMA='rohit' AND c1.COLUMN_NAME='visitid' AND c2.COLUMN_NAME='preid'
""")
print([r[0] for r in cursor.fetchall()])

# Let's look directly - what tables have preid
print("\n=== ALL tables with preid column ===")
cursor.execute("SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND COLUMN_NAME LIKE '%preid%'")
for r in cursor.fetchall(): print(f"  {r[0]}.{r[1]}")

# Maybe preid IS the visitid. Let's check
print("\n=== Does preid 495897 match any visitid? ===")
cursor.execute("SELECT id, patientid, visitno, visitdate FROM fhir_visit_mst WHERE id = 495897 OR visitno = 495897")
rows = cursor.fetchall()
print(f"Visit match: {rows}")

# The REAL prescription lookup: patient->visit->op_initial_assessment->prescription
# But prescription_dtl.hm_id is always 0. Let's check what hm_id actually is
print("\n=== fhir_prescription_dtl where hm_id != 0 ===")
cursor.execute("SELECT COUNT(*) FROM fhir_prescription_dtl WHERE hm_id != 0 AND hm_id IS NOT NULL")
print(f"Non-zero hm_id rows: {cursor.fetchone()[0]}")

# So the real question: how do we get prescriptions for a patient?
# Try: drug_sale_dtl has predtlid linking to prescription_dtl.predetailid
# and drug_sale_mst has patientid. So:
# patient -> drug_sale_mst -> drug_sale_dtl -> prescription_dtl -> drug_mst
print("\n=== Full dispensing+prescription chain for patient 180267 ===")
try:
    cursor.execute("""
        SELECT 
            dsm.drugsaleid, dsm.saledate,
            dsd.qty, dsd.rate,
            d.display AS drug_name,
            pre.dosage, pre.quantity AS prescribed_qty
        FROM fhir_drug_sale_mst dsm
        JOIN fhir_drug_sale_dtl dsd ON dsd.drugsaleid = dsm.drugsaleid
        JOIN fhir_drug_mst d ON d.id = dsd.drugid
        LEFT JOIN fhir_prescription_dtl pre ON pre.predetailid = dsd.predtlid
        WHERE dsm.patientid = 180267
        LIMIT 10
    """)
    rows = cursor.fetchall()
    print(f"Chain rows: {len(rows)}")
    for r in rows: print(f"  {r}")
except Exception as e:
    print(f"Error: {e}")

# Also try a simpler approach - direct drug sale for any visit of patient 180267
# visits: 576473, 579019
print("\n=== Drug sales for visits 576473 or 579019 ===")
cursor.execute("SELECT drugsaleid, patientid, visitid, saledate FROM fhir_drug_sale_mst WHERE visitid IN (576473, 579019)")
rows = cursor.fetchall()
print(f"Rows: {len(rows)}")
for r in rows: print(f"  {r}")

# But the patient's internal id is 180267, check the mst rows
print("\n=== Drug sales directly via patientid=180267 ===")
cursor.execute("SELECT drugsaleid, patientid, visitid, saledate FROM fhir_drug_sale_mst WHERE patientid=180267 LIMIT 5")
rows = cursor.fetchall()
print(f"Rows: {len(rows)}")

# What are the actual patientids in drug_sale_mst?
cursor.execute("SELECT DISTINCT patientid FROM fhir_drug_sale_mst ORDER BY patientid LIMIT 10")
print("Sample patientids in drug_sale_mst:", [r[0] for r in cursor.fetchall()])

conn.close()
print("\nDone.")
