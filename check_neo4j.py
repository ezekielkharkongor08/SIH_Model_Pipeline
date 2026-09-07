from neo4j import GraphDatabase
from agent4_graphRAG.config import settings

def check_neo4j():
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    with driver.session() as session:
        # Check node count
        result = session.run("MATCH (n:Entity) RETURN count(n) as node_count")
        node_count = result.single()["node_count"]
        print(f"Node count: {node_count}")

        # Check sample nodes
        result = session.run("MATCH (n:Entity) RETURN n.canonical_name as name LIMIT 5")
        for record in result:
            print(f"Node name: {record['name']}")

    driver.close()

if __name__ == "__main__":
    check_neo4j()
