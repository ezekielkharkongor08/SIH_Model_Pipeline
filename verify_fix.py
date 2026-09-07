
from agent4_graphRAG.storage.database import GraphRAGRepository
from agent4_graphRAG.models.schemas import GraphRAGQuery

def verify_fix():
    print("Initializing GraphRAG repository...")
    repo = GraphRAGRepository()

    # Query that was returning nothing
    query_text = "Who is mentioned in the FIR documents?"
    print(f"\nQuery: '{query_text}'")

    query = GraphRAGQuery(
        query=query_text,
        max_results=5,
        include_predictions=False
    )

    # Execute query
    result = repo.query_graph(query)

    print(f"  Answer: {result.answer}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Found {len(result.related_nodes)} related nodes")

    repo.close()

if __name__ == "__main__":
    verify_fix()
