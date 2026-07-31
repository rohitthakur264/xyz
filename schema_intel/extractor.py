import sys
import os
import json
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.connection import get_db_connection

def extract_schema():
    """
    Query INFORMATION_SCHEMA to extract tables, columns, and foreign keys.
    Returns a dict mapping table_name -> {'columns': [...], 'fks': [...]}.
    """
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to database for schema extraction.")
        return {}

    db_name = os.getenv("MYSQL_DATABASE", "rohit")
    
    col_query = """
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = %s
    """
    
    fk_query = """
        SELECT 
            TABLE_NAME, 
            COLUMN_NAME, 
            REFERENCED_TABLE_NAME, 
            REFERENCED_COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE REFERENCED_TABLE_SCHEMA = %s
          AND REFERENCED_TABLE_NAME IS NOT NULL
    """
    
    schema_info = defaultdict(lambda: {"columns": [], "fks": []})
    try:
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch columns
        cursor.execute(col_query, (db_name,))
        for row in cursor.fetchall():
            schema_info[row['TABLE_NAME']]['columns'].append({
                'column_name': row['COLUMN_NAME'],
                'data_type': row['DATA_TYPE']
            })
            
        # 2. Fetch declared foreign keys (very few in this DB)
        cursor.execute(fk_query, (db_name,))
        for row in cursor.fetchall():
            schema_info[row['TABLE_NAME']]['fks'].append({
                'column_name': row['COLUMN_NAME'],
                'referenced_table': row['REFERENCED_TABLE_NAME'],
                'referenced_column': row['REFERENCED_COLUMN_NAME']
            })

        # 3. Supplement with manually-known relationships.
        # This HMS database does not declare FK constraints for most tables
        # (~72% have zero declared FKs). These manual relationships tell
        # the LLM how to join tables correctly without guessing from column names.
        #
        # Structure: (table, column, referenced_table, referenced_column)
        manual_fks = [
            # -------------------------------------------------------
            # VERIFIED AGAINST LIVE DB (patient 180267 / reg 165881)
            # -------------------------------------------------------

            # --- PATIENT CORE ---
            # fhir_visit_mst PK is 'id' (NOT visit_id, NOT visitid)
            ("fhir_visit_mst", "patientid", "fhir_patient_mst", "id"),

            # --- BILLING ---
            # fhir_bill_mst.visit_id -> fhir_visit_mst.id  [CONFIRMED: 4 bills returned]
            # fhir_bill_mst also has registration_no — can query directly without join
            ("fhir_bill_mst", "visit_id", "fhir_visit_mst", "id"),

            # --- VITALS ---
            # fhir_patient_vitals: filter directly by patientid OR visit_id -> visit_mst.id
            # CONFIRMED: patient 180267 has 2 rows
            ("fhir_patient_vitals", "patientid", "fhir_patient_mst", "id"),
            ("fhir_patient_vitals", "visit_id", "fhir_visit_mst", "id"),
            # fhir_tprbp_dtl: NO patientid column — must join via visit_id -> visit_mst.id
            # CONFIRMED: 2 rows returned via visit join for patient 180267
            ("fhir_tprbp_dtl", "visit_id", "fhir_visit_mst", "id"),

            # --- ALLERGIES ---
            # fhir_patient_allergy: transactional (has patientid + visitid)
            # fhir_allergies_mst: code/display lookup only — do NOT query for patient records
            ("fhir_patient_allergy", "patientid", "fhir_patient_mst", "id"),
            ("fhir_patient_allergy", "visitid", "fhir_visit_mst", "id"),

            # --- SURGERY / OT ---
            # fhir_ot_scheduling_mst: CONFIRMED 1 row for patient 180267
            # (scheduleid=5154, operationid=1, visitid=579019)
            ("fhir_ot_scheduling_mst", "patientid", "fhir_patient_mst", "id"),
            ("fhir_ot_scheduling_mst", "visitid", "fhir_visit_mst", "id"),
            ("fhir_ot_schedule_mst", "patientid", "fhir_patient_mst", "id"),
            ("fhir_ot_schedule_mst", "visitid", "fhir_visit_mst", "id"),
            ("fhir_otschedule_mst", "patientid", "fhir_patient_mst", "id"),

            # --- ORDERS (service/billing line items) ---
            # fhir_order_mst uses ordpatientid and ordvisitid (NOT patientid/visitid)
            # CONFIRMED: 4 orders for patient 180267
            ("fhir_order_mst", "ordpatientid", "fhir_patient_mst", "id"),
            ("fhir_order_mst", "ordvisitid", "fhir_visit_mst", "id"),
            # fhir_order_dtl: service_id links to fhir_drug_mst.id (drugs) or fhir_service_mst.id
            ("fhir_order_dtl", "order_id", "fhir_order_mst", "ordid"),
            ("fhir_order_dtl", "service_id", "fhir_drug_mst", "id"),

            # --- DRUG DISPENSING ---
            # fhir_drug_sale_mst (with underscore) is the transactional table (1663 rows)
            # NOTE: drug_sale_mst.visitid does NOT match fhir_visit_mst.id — different system
            # For this patient (180267) drug_sale_mst returns 0 rows (no drug sales recorded)
            # Use fhir_order_dtl -> fhir_drug_mst for drug/medication queries instead
            ("fhir_drug_sale_mst", "patientid", "fhir_patient_mst", "id"),
            ("fhir_drug_sale_dtl", "drugsaleid", "fhir_drug_sale_mst", "drugsaleid"),
            ("fhir_drug_sale_dtl", "drugid", "fhir_drug_mst", "id"),
            ("fhir_drug_sale_dtl", "predtlid", "fhir_prescription_dtl", "predetailid"),

            # --- PRESCRIPTIONS (written orders) ---
            # fhir_prescription_dtl: preid is a standalone prescription-event ID
            # Link drugs: prescription_dtl.itemid -> fhir_drug_mst.id  [CONFIRMED]
            ("fhir_prescription_dtl", "itemid", "fhir_drug_mst", "id"),

            # --- LAB TESTS ---
            ("fhir_lab_test_result", "patientid", "fhir_patient_mst", "id"),
            ("fhir_lab_test_result", "visitid", "fhir_visit_mst", "id"),
            ("fhir_lab_test_result", "testid", "fhir_lab_test_mst", "id"),
            ("fhir_lab_test_param", "testid", "fhir_lab_test_mst", "id"),

            # --- DIAGNOSIS ---
            ("fhir_patient_diagnosis", "patientid", "fhir_patient_mst", "id"),
            ("fhir_patient_diagnosis", "visitid", "fhir_visit_mst", "id"),

            # --- ALLOCATION/BED ---
            ("fhir_allocation_mst", "patientid", "fhir_patient_mst", "id"),
            ("fhir_allocation_mst", "visitid", "fhir_visit_mst", "visit_id"),
        ]

        for table_name, column_name, ref_table, ref_column in manual_fks:
            if table_name not in schema_info:
                continue
            already_declared = any(
                fk['column_name'] == column_name and fk['referenced_table'] == ref_table
                for fk in schema_info[table_name]['fks']
            )
            if not already_declared:
                schema_info[table_name]['fks'].append({
                    'column_name': column_name,
                    'referenced_table': ref_table,
                    'referenced_column': ref_column
                })
                
    except Exception as e:
        print(f"Error querying schema: {e}")
    finally:
        if conn.is_connected():
            conn.close()
            
    return dict(schema_info)

def cache_schema():
    schema = extract_schema()
    if not schema:
        return

    # Sanity check: warn if prescription detail has no patient link
    pre_master_tables = [
        t for t, info in schema.items()
        if any(c['column_name'] == 'preid' for c in info['columns'])
        and any(c['column_name'] == 'patientid' for c in info['columns'])
        and t != 'fhir_prescription_dtl'
    ]
    if not pre_master_tables:
        print(
            "NOTE: No single table combines 'preid' + 'patientid'. "
            "Using fhir_drugsale_mst (patientid+visitid) as the "
            "prescription dispensing source. This is expected for this HMS DB."
        )

    cache_path = os.path.join(os.path.dirname(__file__), "schema_cache.json")
    with open(cache_path, 'w') as f:
        json.dump(schema, f, indent=4)
    print(f"Schema cached to {cache_path} ({len(schema)} tables).")
    return schema

if __name__ == "__main__":
    cache_schema()
