
from agent4_graphRAG.storage.database import GraphRAGRepository
from agent4_graphRAG.models.schemas import GraphRAGQuery

def verify_specific_query(query_text):
    print(f"Initializing GraphRAG repository for query: '{query_text}'...")
    repo = GraphRAGRepository()

    query = GraphRAGQuery(
        query=query_text,
        max_results=5,
        include_predictions=False
    )

    result = repo.query_graph(query)

    print(f"  Answer: {result.answer}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Found {len(result.related_nodes)} related nodes")

    repo.close()

if __name__ == "__main__":
    verify_specific_query("Who is Rajesh Sharma?")
    verify_specific_query("Who is mentioned in the FIR documents?")
