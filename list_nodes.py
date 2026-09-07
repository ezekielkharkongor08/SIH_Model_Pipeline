from neo4j import GraphDatabase
from agent4_graphRAG.config import settings

def list_nodes():
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    with driver.session() as session:
        # Check node types
        result = session.run("MATCH (n:Entity) WHERE n.entity_type IN ['PERSON', 'ORGANIZATION'] RETURN n.canonical_name as name, n.entity_type as type")
        for record in result:
            print(f"Name: {record['name']}, Type: {record['type']}")

    driver.close()

if __name__ == "__main__":
    list_nodes()
