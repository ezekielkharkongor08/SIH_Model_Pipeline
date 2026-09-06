#!/usr/bin/env python3
"""
demo_agent4_graphrag.py

Demonstration of Agent 4 GraphRAG - Natural language query interface
for the knowledge graph built by Agents 1, 2, and 3.

This demo shows how to query the knowledge graph using natural language.
"""

import time
import requests
from loguru import logger

# Configure logging
logger.add("demo_graphrag.log", level="INFO", rotation="1 MB")


def demo_api_queries():
    """Demo GraphRAG queries via API."""

    print("\n" + "=" * 80)
    print("AGENT 4 - GRAPHRAG API DEMO")
    print("=" * 80)

    base_url = "http://localhost:8003"

    # First, get some example queries
    print("\n1. Getting example queries...")
    try:
        response = requests.get(f"{base_url}/api/v1/graphrag/examples")
        examples = response.json()
        print("   Example queries:")
        for cat in examples["examples"]:
            print(f"   {cat['category']}:")
            for q in cat["queries"]:
                print(f"     - {q}")
    except Exception as e:
        print(f"   Could not fetch examples (API may not be running): {e}")

    # Sample queries to test
    sample_queries = [
        "Who works at TechCorp?",
        "What is the relationship between Rajesh Sharma and Priya Malhotra?",
        "How is Rajesh Sharma connected to Mumbai?",
    ]

    print("\n" + "-" * 80)
    print("Testing sample queries:")
    print("-" * 80)

    for query in sample_queries:
        print(f"\nQuery: '{query}'")

        # POST request
        try:
            response = requests.post(
                f"{base_url}/api/v1/graphrag/query",
                json={"query": query, "max_results": 5}
            )
            result = response.json()

            if result["success"]:
                print(f"  Answer: {result['result']['answer'][:200]}...")
                print(f"  Confidence: {result['result']['confidence']:.2f}")
                print(f"  From cache: {result['from_cache']}")
                print(f"  Time: {result['result']['query_time_ms']:.1f}ms")
            else:
                print(f"  Error: {result.get('detail', 'Unknown error')}")

        except requests.exceptions.ConnectionError:
            print(f"  API not running at {base_url}")
            print("  Start with: python main_agent4.py")
            break
        except Exception as e:
            print(f"  Error: {e}")


def demo_direct_usage():
    """Demo GraphRAG by importing and using directly."""

    print("\n" + "=" * 80)
    print("AGENT 4 - DIRECT PYTHON USAGE DEMO")
    print("=" * 80)

    try:
        from agent4_graphRAG.storage.database import GraphRAGRepository
        from agent4_graphRAG.models.schemas import GraphRAGQuery

        print("\nInitializing GraphRAG repository...")

        repo = GraphRAGRepository()
        print("✓ Repository initialized")

        # Sample queries
        queries = [
            "Who works at TechCorp?",
            "What is the relationship between Rajesh Sharma and Priya Malhotra?",
        ]

        print("\nExecuting queries...")

        for query_text in queries:
            print(f"\nQuery: '{query_text}'")

            # Create query object
            query = GraphRAGQuery(
                query=query_text,
                max_results=5,
                include_predictions=False
            )

            # Execute query
            result = repo.query_graph(query)

            print(f"  Answer: {result.answer[:200]}...")
            print(f"  Confidence: {result.confidence:.2f}")
            print(f"  Time: {result.query_time_ms:.1f}ms")

            if result.related_nodes:
                print(f"  Found {len(result.related_nodes)} related nodes")

            if result.related_paths:
                print(f"  Found {len(result.related_paths)} related paths")

        # Show stats
        print("\n" + "-" * 80)
        print("Query Statistics:")
        print("-" * 80)
        stats = repo.stats
        print(f"  Total queries: {stats.total_queries}")
        print(f"  Average time: {stats.avg_query_time_ms:.1f}ms")
        print(f"  Cache hits: {stats.cache_hits}")
        print(f"  Cache misses: {stats.cache_misses}")

        # Close connection
        repo.close()

    except Exception as e:
        print(f"\nError during direct usage demo:")
        print(f"  {e}")
        print("\n  Make sure Neo4j is running and properly configured.")
        print("  Update neo4j credentials in .env or agent4_graphRAG/config.py")


def demo_pipeline_flow():
    """Show the complete flow from Agent 1 to Agent 4."""

    print("\n" + "=" * 80)
    print("COMPLETE PIPELINE FLOW: Agents 1 -> 2 -> 3 -> 4")
    print("=" * 80)

    print("""
This demonstrates how all agents work together:

┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   Agent 1       │    │   Agent 2        │    │   Agent 3        │
│   (Extraction)  │ ──▶│   (Resolution)   │ ──▶│   (Graph Builder)  │
│   - Extracts    │    │   - Clusters     │    │   - Builds         │
│     entities     │    │     entities       │    │     knowledge     │
│     triples      │    │   - Generates    │    │       graph        │
└─────────────────┘    │     embeddings     │    └────────┬─────────┘
                       └──────────────────┘               │
                                                          │
                                                          ▼
                                                 ┌──────────────────┐
                                                 │   Agent 4        │
                                                 │   (GraphRAG)     │
                                                 │   - Query with   │
                                                 │     natural lang │
                                                 └──────────────────┘

Key Integration Points:
1. Agent 1 stores raw entities and triples in PostgreSQL
2. Agent 2 resolves entities, creates clusters, stores BGE-m3 embeddings in pgvector
3. Agent 3 builds knowledge graph (nodes from clusters, edges from resolved_triples)
4. Agent 3 exports graph to Neo4j
5. Agent 4 queries Neo4j using natural language

The GraphRAG pipeline flow:
1. Natural language query comes in
2. GraphRAG extracts entities from the query
3. Searches Neo4j for matching nodes
4. Finds paths/relationships between nodes
5. Generates natural language answer with confidence score
    """)


if __name__ == "__main__":
    try:
        # Show the pipeline flow first
        demo_pipeline_flow()

        # Demo direct Python usage
        demo_direct_usage()

        # Demo API queries (only if API is running)
        print("\n" + "=" * 80)
        print("API DEMO")
        print("=" * 80)
        print("\nNote: This requires the Agent 4 API server to be running.")
        print("Start it with: python main_agent4.py")
        demo_api_queries()

        print("\n" + "=" * 80)
        print("DEMO COMPLETE")
        print("=" * 80 + "\n")

    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)
        print(f"\nDemo failed: {e}\n")
