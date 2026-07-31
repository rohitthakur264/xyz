from db.connection import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("=== Row counts ===")
for t in ['fhir_drug_sale_mst', 'fhir_drugsale_mst', 'fhir_drug_sale_dtl', 'fhir_prescription_dtl']:
    cursor.execute(f"SELECT COUNT(*) FROM `{t}`")
    print(f"  {t}: {cursor.fetchone()[0]} rows")

print("\n=== fhir_drug_sale_mst columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_drug_sale_mst' ORDER BY ORDINAL_POSITION LIMIT 20")
print([r[0] for r in cursor.fetchall()])

print("\n=== fhir_drugsale_mst columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_drugsale_mst' ORDER BY ORDINAL_POSITION LIMIT 20")
print([r[0] for r in cursor.fetchall()])

print("\n=== fhir_drug_sale_dtl key columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_drug_sale_dtl' ORDER BY ORDINAL_POSITION LIMIT 20")
print([r[0] for r in cursor.fetchall()])

print("\n=== Join test: drug_sale_dtl -> drug_sale_mst ===")
try:
    cursor.execute("""
        SELECT dtl.drugsaleid, mst.drugsaleid, mst.patientid, mst.visitid
        FROM fhir_drug_sale_dtl dtl
        JOIN fhir_drug_sale_mst mst ON dtl.drugsaleid = mst.drugsaleid
        LIMIT 5
    """)
    rows = cursor.fetchall()
    print(f"  Rows returned: {len(rows)}")
    for r in rows:
        print(f"  {r}")
except Exception as e:
    print(f"  Error: {e}")

print("\n=== Check predtlid in drug_sale_dtl -> prescription_dtl ===")
try:
    cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_drug_sale_dtl' AND COLUMN_NAME IN ('predtlid','preid','predetailid','prescriptionid')")
    cols = [r[0] for r in cursor.fetchall()]
    print(f"  Link columns found: {cols}")
    
    if 'predtlid' in cols:
        cursor.execute("""
            SELECT dtl.predtlid, pre.predetailid, pre.preid
            FROM fhir_drug_sale_dtl dtl
            JOIN fhir_prescription_dtl pre ON dtl.predtlid = pre.predetailid
            LIMIT 3
        """)
        rows = cursor.fetchall()
        print(f"  predtlid -> prescription_dtl join returned {len(rows)} rows")
        for r in rows:
            print(f"  {r}")
except Exception as e:
    print(f"  Error: {e}")

print("\n=== Sample drug_sale_mst for patient 180267 ===")
try:
    cursor.execute("SELECT drugsaleid, patientid, visitid, saledate, netamount FROM fhir_drug_sale_mst WHERE patientid=180267 LIMIT 5")
    rows = cursor.fetchall()
    print(f"  Rows: {len(rows)}")
    for r in rows:
        print(f"  {r}")
except Exception as e:
    print(f"  Error: {e}")

conn.close()
print("\nDone.")
