from agent2_resolution.storage.database import ResolutionRepository
from agent2_resolution.embeddings.embedder import BGEEmbedder

def test_similarity():
    repo = ResolutionRepository()
    embedder = BGEEmbedder()

    # Query: "Ananya Rao"
    query = "Ananya Rao"
    embedding = embedder.embed(query).tolist()

    results = repo.find_similar_clusters(embedding=embedding, top_k=5, threshold=0.5)
    print(f"Results for '{query}': {results}")

if __name__ == "__main__":
    test_similarity()
