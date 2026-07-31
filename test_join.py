import sqlglot

def check_joins(sql_query, retrieved_schema):
    parsed = sqlglot.parse_one(sql_query, read="mysql")
    
    # Build alias map to know which alias corresponds to which table
    alias_to_table = {}
    for table_node in parsed.find_all(sqlglot.exp.Table):
        alias = table_node.alias or table_node.name
        alias_to_table[alias] = table_node.name

    for join in parsed.find_all(sqlglot.exp.Join):
        on_clause = join.args.get("on")
        if not on_clause:
            continue
            
        for eq in on_clause.find_all(sqlglot.exp.EQ):
            cols = list(eq.find_all(sqlglot.exp.Column))
            if len(cols) == 2:
                c1, c2 = cols[0], cols[1]
                t1 = alias_to_table.get(c1.table) or c1.table
                t2 = alias_to_table.get(c2.table) or c2.table
                col1 = c1.name
                col2 = c2.name
                
                if not t1 or not t2:
                    continue
                
                # Check if there is an FK from t1.col1 -> t2
                if t1 in retrieved_schema:
                    for fk in retrieved_schema[t1].get('fks', []):
                        if fk['column_name'] == col1 and fk['referenced_table'] == t2:
                            if fk['referenced_column'] != col2:
                                return f"FK mismatch: {t1}.{col1} should join to {t2}.{fk['referenced_column']}, not {col2}."
                
                # Check if there is an FK from t2.col2 -> t1
                if t2 in retrieved_schema:
                    for fk in retrieved_schema[t2].get('fks', []):
                        if fk['column_name'] == col2 and fk['referenced_table'] == t1:
                            if fk['referenced_column'] != col1:
                                return f"FK mismatch: {t2}.{col2} should join to {t1}.{fk['referenced_column']}, not {col1}."
                                
    return "OK"

schema = {
    "fhir_patient_mst": {
        "fks": [
            {"column_name": "gender", "referenced_table": "fhir_gender_mst", "referenced_column": "id"}
        ]
    },
    "fhir_gender_mst": {"fks": []}
}

print(check_joins("SELECT * FROM fhir_patient_mst p JOIN fhir_gender_mst g ON p.gender = g.code", schema))
print(check_joins("SELECT * FROM fhir_patient_mst p JOIN fhir_gender_mst g ON p.gender = g.id", schema))
