from db.connection import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("=== Tables with 'preid' column (prescription) ===")
cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND COLUMN_NAME='preid'")
print([r[0] for r in cursor.fetchall()])

print("\n=== Tables with billing-related columns ===")
cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND COLUMN_NAME IN ('billamount','totalamount','netamount') GROUP BY TABLE_NAME")
print([r[0] for r in cursor.fetchall()])

print("\n=== Tables with vitals columns (pulse, spo2, temperature) ===")
cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND COLUMN_NAME IN ('pulse','spo2','temperature') GROUP BY TABLE_NAME")
print([r[0] for r in cursor.fetchall()])

print("\n=== Tables with allergyid ===")
cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND COLUMN_NAME='allergyid' GROUP BY TABLE_NAME")
print([r[0] for r in cursor.fetchall()])

print("\n=== Tables with surgery/OT columns (scheduleid, surgeonid, scheduledate) ===")
cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='rohit' AND COLUMN_NAME IN ('scheduleid','surgeonid','scheduledate') GROUP BY TABLE_NAME")
print([r[0] for r in cursor.fetchall()])

print("\n=== Tables with patientid + visitid (key join tables) ===")
cursor.execute("""
    SELECT c1.TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS c1
    JOIN INFORMATION_SCHEMA.COLUMNS c2 ON c1.TABLE_NAME=c2.TABLE_NAME AND c1.TABLE_SCHEMA=c2.TABLE_SCHEMA
    WHERE c1.TABLE_SCHEMA='rohit' AND c1.COLUMN_NAME='patientid' AND c2.COLUMN_NAME='visitid'
    ORDER BY c1.TABLE_NAME
""")
print([r[0] for r in cursor.fetchall()])

conn.close()
print("\n=== Done ===")
