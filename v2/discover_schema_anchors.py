import sys
import os
import json

v2_dir = os.path.dirname(os.path.abspath(__file__))
if v2_dir not in sys.path:
    sys.path.insert(0, v2_dir)

from database.schema_loader import SchemaLoader
from database.schema_anchors import find_anchor_tables, merge_extra_relationships, MAPPINGS_FILE
from config.logging import get_logger

logger = get_logger("anchor_discovery")

LOOKUP_KEYWORDS = {
    "gender": ["gender"],
    "nationality": ["national"],
    "marital_status": ["marital"],
    "department": ["dept", "department"],
    "doctor": ["emp", "user", "doctor", "doc"],
    "ward": ["ward"],
    "room": ["room"],
    "bed": ["bed"],
    "allergy_nurse": ["nurse_assessment"],
    "allergy_general": ["allergies_mst"],
    "allergy_food": ["allergyfoodmst"],
    "allergy_medicine": ["allergymedicinemst"],
    "vitals": ["tprbp"],
    "lab_result": ["lab_test_result"],
    "radiology_result": ["rad_imgresult"],
    "radiology_services": ["rad_imgservices"],
    "radiology_template": ["rad_testtemplate"],
    "prescription_master": ["prescription_mst"],
    "prescription_detail": ["prescription_dtl"],
    "drug": ["drug_mst"],
    "frequency": ["prescription_frequency"],
    "operation_scheduling": ["ot_scheduling_mst"],
    "operation_detail": ["ot_schedulling_dtl"],
    "service": ["service_mst"],
    "assessment": ["assessment", "initial"],
}

def discover_anchors(full_schema: dict, pat_table: str, vis_table: str):
    anchors = {}
    source_tier = {}
    
    # 1. Forward FKs (Safest)
    for source_table in [pat_table, vis_table]:
        if not source_table or source_table not in full_schema: continue
        for fk in full_schema[source_table].get("foreign_keys", []):
            ref_table = fk["referenced_table"]
            for name, kws in LOOKUP_KEYWORDS.items():
                if any(kw in ref_table.lower() for kw in kws):
                    if name not in anchors:
                        anchors[name] = ref_table
                        source_tier[name] = "forward_fk"
                    
    # 2. Reverse FKs
    for table, meta in full_schema.items():
        for fk in meta.get("foreign_keys", []):
            if fk["referenced_table"] in [pat_table, vis_table]:
                for name, kws in LOOKUP_KEYWORDS.items():
                    if any(kw in table.lower() for kw in kws):
                        if name not in anchors:
                            anchors[name] = table
                            source_tier[name] = "reverse_fk"
                        
    # 3. Global Schema Search (For tables without FKs to core)
    for table in full_schema.keys():
        for name, kws in LOOKUP_KEYWORDS.items():
            if any(kw in table.lower() for kw in kws):
                if name not in anchors:
                    anchors[name] = table
                    source_tier[name] = "global_search_UNVERIFIED"
                
    return anchors, source_tier

def main():
    print("Loading live database schema...")
    loader = SchemaLoader()
    schema = loader.load_schema()
    merge_extra_relationships(schema)
    
    core_anchors = find_anchor_tables(schema)
    pat_table = core_anchors.get("patient")
    vis_table = core_anchors.get("visit")
    
    anchors, source_tier = discover_anchors(schema, pat_table, vis_table)
    final_anchors = {**core_anchors, **anchors}
    
    print("\n=== Discovered Anchors ===")
    for name, table in final_anchors.items():
        tier = source_tier.get(name, "core")
        flag = " ?? VERIFY MANUALLY (found via risky global search)" if tier == "global_search_UNVERIFIED" else ""
        print(f"  {name}: {table}  [{tier}]{flag}")
        
    confirm = input("\nIs this mapping correct? Type 'y' to freeze, anything else to abort: ")
    if confirm.strip().lower() != "y":
        print("Aborted. table_mappings.json NOT written.")
        return
        
    os.makedirs(os.path.dirname(MAPPINGS_FILE), exist_ok=True)
    with open(MAPPINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(final_anchors, f, indent=2)
    print(f"SUCCESS: Frozen to {MAPPINGS_FILE}")

if __name__ == "__main__":
    main()
