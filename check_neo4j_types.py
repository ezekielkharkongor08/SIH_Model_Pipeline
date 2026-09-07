from neo4j import GraphDatabase
from agent4_graphRAG.config import settings

def check_neo4j_types():
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    with driver.session() as session:
        # Check node types
        result = session.run("MATCH (n:Entity) RETURN n.entity_type as type, count(n) as count GROUP BY type")
        for record in result:
            print(f"Type: {record['type']}, Count: {record['count']}")

    driver.close()

if __name__ == "__main__":
    check_neo4j_types()
