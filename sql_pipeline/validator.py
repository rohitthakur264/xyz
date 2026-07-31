import sqlglot
from config.settings import SQL_ROW_LIMIT

def validate_sql(sql_query, retrieved_schema, active_patient=None):
    """
    Validates the generated SQL using sqlglot:
    1. Must be a SELECT statement.
    2. Must only query tables present in retrieved_schema.
    3. Must only use columns present in the table schema.
    4. Applies a LIMIT 50 if none exists.
    Returns (validated_sql_string, error_msg). If valid, error_msg is None.
    """
    try:
        parsed = sqlglot.parse_one(sql_query, read="mysql")
    except Exception as e:
        return None, f"Failed to parse SQL: {e}"

    if not isinstance(parsed, sqlglot.exp.Select):
        return None, "Only SELECT statements are allowed."

    # Validate tables
    tables_in_query = {t.name for t in parsed.find_all(sqlglot.exp.Table)}
    allowed_tables = set(retrieved_schema.keys())
    if not tables_in_query.issubset(allowed_tables):
        return None, f"Query references tables outside the allowed set: {tables_in_query - allowed_tables}"

    # NEW: if more than one table is involved, every column must be qualified.
    if len(tables_in_query) > 1:
        unqualified = [c.name for c in parsed.find_all(sqlglot.exp.Column) if not c.table]
        if unqualified:
            return None, (
                f"Column(s) {unqualified} must be prefixed with a table alias "
                f"since this query joins multiple tables (e.g. p.{unqualified[0]})."
            )

    used_tables = tables_in_query

    # NEW: Validate foreign key joins against the schema
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
                col1, col2 = c1.name, c2.name
                
                if not t1 or not t2:
                    continue
                
                # Check if there is an FK from t1.col1 -> t2
                if t1 in retrieved_schema:
                    for fk in retrieved_schema[t1].get('fks', []):
                        if fk['column_name'] == col1 and fk['referenced_table'] == t2:
                            if fk['referenced_column'] != col2:
                                return None, f"FK mismatch: {t1}.{col1} MUST join to {t2}.{fk['referenced_column']}, not {col2}."
                
                # Check if there is an FK from t2.col2 -> t1
                if t2 in retrieved_schema:
                    for fk in retrieved_schema[t2].get('fks', []):
                        if fk['column_name'] == col2 and fk['referenced_table'] == t1:
                            if fk['referenced_column'] != col1:
                                return None, f"FK mismatch: {t2}.{col2} MUST join to {t1}.{fk['referenced_column']}, not {col1}."

    # Validate columns
    has_patient_column = False
    for t in used_tables:
        if t in retrieved_schema:
            valid_cols = [c['column_name'] for c in retrieved_schema[t]['columns']]
            if any(col in valid_cols for col in ['registration_no', 'patientid', 'patient_id', 'oldregistration_no']):
                has_patient_column = True
                break

    if not active_patient and has_patient_column:
        if not parsed.args.get('where'):
            return None, "NEEDS_PATIENT: Which patient? Please provide a registration number, patient ID, or name."

    for column in parsed.find_all(sqlglot.exp.Column):
        col_name = column.name
        if col_name == "*":
            continue
            
        found = False
        for t in used_tables:
            if t in retrieved_schema:
                valid_cols = [c['column_name'] for c in retrieved_schema[t]['columns']]
                if col_name in valid_cols:
                    found = True
                    break
        if not found:
            return None, f"Column '{col_name}' does not exist in any of the queried tables."

    # Enforce LIMIT 50
    limit_exp = parsed.args.get("limit")
    if not limit_exp:
        parsed = parsed.limit(SQL_ROW_LIMIT)

    return parsed.sql(dialect="mysql"), None
