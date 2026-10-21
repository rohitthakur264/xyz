import mysql.connector
from dotenv import load_dotenv
load_dotenv('.env')
import os
conn = mysql.connector.connect(
    host=os.getenv('DB_HOST'),
    port=int(os.getenv('DB_PORT')),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cursor = conn.cursor()
cursor.execute('DESCRIBE fhir_rad_imgservices')
for row in cursor.fetchall():
    print(row)
