import networkx as nx
from collections import deque
from config.logging import get_logger

logger = get_logger(__name__)

class RelationshipGraph:
    """Builds a bidirectional graph of table relationships to discover JOIN paths."""
    
    def __init__(self, schema: dict):
        self.schema = schema
        self.graph = nx.Graph()
        self._build_graph()

    def _build_graph(self):
        """Populate the NetworkX graph with tables and foreign key edges."""
        # Add nodes
        for table in self.schema:
            self.graph.add_node(table)
            
        # Add edges
        for table, info in self.schema.items():
            for fk in info.get("foreign_keys", []):
                ref_table = fk["referenced_table"]
                if ref_table in self.schema:
                    # We store the column names as edge data so we can construct the ON clause later
                    self.graph.add_edge(
                        table, 
                        ref_table, 
                        source_col=fk["column_name"], 
                        target_col=fk["referenced_column"]
                    )
        logger.info(f"Built relationship graph with {self.graph.number_of_nodes()} tables and {self.graph.number_of_edges()} relationships.")

    def find_shortest_path(self, start_table: str, end_table: str) -> list:
        """Find the shortest sequence of tables connecting start_table and end_table."""
        if start_table not in self.graph or end_table not in self.graph:
            return []
        
        try:
            path = nx.shortest_path(self.graph, source=start_table, target=end_table)
            return path
        except nx.NetworkXNoPath:
            return []
            
    def get_join_conditions(self, path: list) -> list:
        """Given a path of tables, return the list of JOIN conditions connecting them."""
        joins = []
        for i in range(len(path) - 1):
            t1 = path[i]
            t2 = path[i + 1]
            edge_data = self.graph.get_edge_data(t1, t2)
            
            # NetworkX Graph is undirected, so we need to check which direction the edge was originally added
            # to know which column belongs to which table. 
            # We can cross-reference the schema.
            t1_fk = next((fk for fk in self.schema[t1]["foreign_keys"] if fk["referenced_table"] == t2), None)
            if t1_fk:
                joins.append(f"{t1}.{t1_fk['column_name']} = {t2}.{t1_fk['referenced_column']}")
            else:
                t2_fk = next((fk for fk in self.schema[t2]["foreign_keys"] if fk["referenced_table"] == t1), None)
                if t2_fk:
                    joins.append(f"{t2}.{t2_fk['column_name']} = {t1}.{t2_fk['referenced_column']}")
        return joins

    def populate_schema_relationships(self):
        """Mutate the schema to inject 1st-degree relationships for embedding."""
        for table in self.schema:
            neighbors = list(self.graph.neighbors(table))
            self.schema[table]["relationships"] = neighbors
