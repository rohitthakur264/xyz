class EmbeddingBuilder:
    """Builds rich text representations of schema tables for embedding."""
    
    @staticmethod
    def build_table_embedding_text(table_info: dict) -> str:
        """Converts a table schema dictionary into a descriptive string for Chroma."""
        name = table_info.get("table") or table_info.get("table_name", "unknown")
        desc = table_info.get("description", f"Table storing {name} data")
        
        columns = ", ".join([f"{c['column_name']} ({c.get('data_type', 'str')})" for c in table_info.get("columns", [])])
        pk = table_info.get("primary_key", "None")
        fks = ", ".join([f"{f['column_name']} -> {f.get('referenced_table', '')}.{f.get('referenced_column', '')}" for f in table_info.get("foreign_keys", []) if isinstance(f, dict)])
        rels = ", ".join(table_info.get("relationships", []))
        
        text = f"Table: {name}\n"
        text += f"Description: {desc}\n"
        text += f"Primary Key: {pk}\n"
        text += f"Columns: {columns}\n"
        if fks:
            text += f"Foreign Keys: {fks}\n"
        if rels:
            text += f"Related Tables: {rels}\n"
            
        return text

    @staticmethod
    def build_table_metadata(table_info: dict) -> dict:
        """Builds filtering metadata for a table."""
        tbl_name = table_info.get("table") or table_info.get("table_name", "")
        name = tbl_name.lower()
        module = "General"
        if "patient" in name: module = "Patient"
        elif "visit" in name or "encounter" in name: module = "Visit"
        elif "bill" in name or "account" in name: module = "Billing"
        elif "drug" in name or "prescription" in name: module = "Pharmacy"
        elif "lab" in name: module = "Laboratory"
        elif "allergy" in name: module = "Allergy"
        
        return {
            "table": tbl_name,
            "table_name": tbl_name,
            "module": module,
            "type": "schema"
        }
