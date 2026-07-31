from db.connection import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# CRITICAL FINDINGS:
# 1. fhir_drug_sale_mst.visitid does NOT match fhir_visit_mst.id (562027 not in visit_mst)
#    -> drug_sale_mst is from a DIFFERENT system/schema snapshot. No match for patient 180267.
# 2. fhir_order_mst uses ordpatientid (not patientid) and ordvisitid
# 3. fhir_order_mst HAS rows for patient 180267 (4 orders: Apr+Jun 2026)
# 4. fhir_tprbp_dtl uses visit_id (not visitid, not patientid directly)
# 5. fhir_tprbp_dtl HAS 2 rows for patient via visitids 576473, 579019

# So the REAL prescription path via order system:
print("=== fhir_order_dtl for patient 180267 (via ordid) ===")
cursor.execute("""
    SELECT od.id, od.order_id, od.patient_id, od.service_id, od.netamount, od.orddatetime
    FROM fhir_order_mst om
    JOIN fhir_order_dtl od ON od.order_id = om.ordid
    WHERE om.ordpatientid = 180267
    LIMIT 10
""")
rows = cursor.fetchall()
print(f"Rows: {len(rows)}")
for r in rows: print(f"  {r}")

# What is service_id? Does it link to drug_mst?
if rows:
    sample_sids = list(set(r[3] for r in rows[:5]))
    cursor.execute(f"SELECT id, display, itemtypeid FROM fhir_drug_mst WHERE id IN ({','.join(str(x) for x in sample_sids)}) LIMIT 5")
    print("service_id -> drug_mst:", cursor.fetchall())
    
    # Also check fhir_service_mst
    cursor.execute(f"SELECT id, display FROM fhir_service_mst WHERE id IN ({','.join(str(x) for x in sample_sids)}) LIMIT 5")
    print("service_id -> service_mst:", cursor.fetchall())

# Verify tprbp_dtl has visit_id not visitid + patientid
print("\n=== fhir_tprbp_dtl: how to filter for patient? ===")
print("Confirmed: tprbp_dtl has NO patientid. Filter via visit_id IN (patient's visitids)")
cursor.execute("""
    SELECT tp.tprbp_id, tp.visit_id, tp.pulse, tp.systolic, tp.diastolic, tp.temperature, tp.reading_datetime
    FROM fhir_tprbp_dtl tp
    JOIN fhir_visit_mst v ON tp.visit_id = v.id
    WHERE v.patientid = 180267
    LIMIT 5
""")
rows = cursor.fetchall()
print(f"tprbp via visit join: {len(rows)} rows")
for r in rows: print(f"  {r}")

# Get the final confirmed join paths for all domains
print("\n=== CONFIRMED WORKING QUERIES FOR PATIENT 180267 ===")

print("\n[VITALS - fhir_patient_vitals]")
cursor.execute("SELECT id, visit_id, pulse, systolic, diastolic, temperature, reading_datetime FROM fhir_patient_vitals WHERE patientid=180267")
rows = cursor.fetchall()
print(f"  Direct patientid: {len(rows)} rows -> {rows}")

print("\n[VITALS - fhir_tprbp_dtl via visit join]")
cursor.execute("""
    SELECT tp.tprbp_id, v.patientid, tp.pulse, tp.systolic, tp.diastolic
    FROM fhir_tprbp_dtl tp JOIN fhir_visit_mst v ON tp.visit_id = v.id
    WHERE v.patientid = 180267
""")
rows = cursor.fetchall()
print(f"  Via visit join: {len(rows)} rows")

print("\n[BILLING - direct registration_no]")
cursor.execute("SELECT billno, visit_id, netamount, billdate FROM fhir_bill_mst WHERE registration_no='165881'")
rows = cursor.fetchall()
print(f"  {len(rows)} bills: {[r[0] for r in rows]}")

print("\n[OT SURGERY - fhir_ot_scheduling_mst]")
cursor.execute("SELECT scheduleid, visitid, operationid, operationdate FROM fhir_ot_scheduling_mst WHERE patientid=180267")
rows = cursor.fetchall()
print(f"  {len(rows)} rows: {rows}")

print("\n[PRESCRIPTIONS - fhir_prescription_dtl via fhir_order_mst]")
cursor.execute("""
    SELECT pre.preid, pre.itemid, d.display AS drug, pre.dosage, pre.quantity
    FROM fhir_order_mst om
    JOIN fhir_prescription_dtl pre ON pre.preid = om.ordid
    LEFT JOIN fhir_drug_mst d ON d.id = pre.itemid
    WHERE om.ordpatientid = 180267
    LIMIT 10
""")
rows = cursor.fetchall()
print(f"  preid=ordid join: {len(rows)} rows")
for r in rows: print(f"    {r}")

conn.close()
print("\nDone.")
