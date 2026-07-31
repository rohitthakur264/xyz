from db.connection import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check allergy table columns
print("=== fhir_patient_allergy columns ===")
cursor.execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_patient_allergy' ORDER BY ORDINAL_POSITION")
for r in cursor.fetchall():
    print(f"  {r[0]} ({r[1]})")

# Check prescription_dtl columns
print("\n=== fhir_prescription_dtl key columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_prescription_dtl' AND COLUMN_NAME IN ('preid','patientid','visitid','visit_id','drugid','drug_id','dosage','qty','quantity')")
for r in cursor.fetchall():
    print(f"  {r[0]}")

# Check if there's a prescription mst table we missed
print("\n=== All fhir tables with 'prescription' or 'pre' in name ===")
cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME LIKE '%presc%'")
print([r[0] for r in cursor.fetchall()])

# Check bill_mst key columns
print("\n=== fhir_bill_mst key columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_bill_mst' AND COLUMN_NAME IN ('patientid','visitid','visit_id','billamount','totalamount','netamount','billno','billdate')")
for r in cursor.fetchall():
    print(f"  {r[0]}")

# Check OT scheduling mst
print("\n=== fhir_ot_scheduling_mst key columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_ot_scheduling_mst' AND COLUMN_NAME IN ('patientid','visitid','visit_id','scheduleid','scheduledate','surgeonid','procedurename','operationname')")
for r in cursor.fetchall():
    print(f"  {r[0]}")

# Check fhir_ot_schedule_mst
print("\n=== fhir_ot_schedule_mst key columns ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_ot_schedule_mst' AND COLUMN_NAME IN ('patientid','visitid','visit_id','scheduleid','scheduledate','surgeonid','procedurename','operationname')")
for r in cursor.fetchall():
    print(f"  {r[0]}")

# Get drug_sale_mst columns related to prescription/drug
print("\n=== fhir_drugsale_mst key cols ===")
cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND TABLE_NAME='fhir_drugsale_mst' AND COLUMN_NAME IN ('patientid','visitid','drugid','preid','qty','amount','saledate')")
for r in cursor.fetchall():
    print(f"  {r[0]}")

conn.close()
print("\nDone.")
