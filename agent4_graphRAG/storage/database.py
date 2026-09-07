"""
storage/database.py — Data access layer for Agent 4 GraphRAG
Responsibility: Query knowledge graph from Neo4j and PostgreSQL for context retrieval.
"""

import hashlib
import json
import time
import httpx
from typing import List, Dict, Optional, Tuple, Any
from loguru import logger
from neo4j import GraphDatabase
from agent4_graphRAG.config import settings
from agent4_graphRAG.models.schemas import GraphRAGQuery, GraphRAGResult, GraphRAGStats

# Ponytail: Reuse Agent 2 resolution infra for vector search
from agent2_resolution.embeddings.embedder import BGEEmbedder
from agent2_resolution.storage.database import ResolutionRepository


class GraphRAGRepository:
    """Repository for querying knowledge graph and generating context for LLMs."""

    def __init__(self):
        # Neo4j connection for graph traversal
        self.neo4j_driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )

        # Ponytail: Reuse Agent 2 resolution infra
        self.embedder = BGEEmbedder()
        self.resolution_repo = ResolutionRepository()

        # Simple in-memory cache for query results
        self._query_cache: Dict[str, Tuple[GraphRAGResult, float]] = {}

        # Statistics tracking
        self.stats = GraphRAGStats()

    def _clear_expired_cache(self):
        """Remove expired cache entries."""
        if not settings.ENABLE_QUERY_CACHE:
            return

        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self._query_cache.items()
            if current_time - timestamp > settings.QUERY_CACHE_TTL
        ]
        for key in expired_keys:
            del self._query_cache[key]

    def _get_cache_key(self, query: GraphRAGQuery) -> str:
        """Generate a cache key for the query."""
        query_str = f"{query.query}:{query.run_id}:{query.include_predictions}:{query.max_results}"
        return hashlib.md5(query_str.encode()).hexdigest()

    def _get_from_cache(self, cache_key: str) -> Optional[GraphRAGResult]:
        """Get result from cache if available and not expired."""
        if not settings.ENABLE_QUERY_CACHE:
            return None

        if cache_key in self._query_cache:
            result, timestamp = self._query_cache[cache_key]
            if time.time() - timestamp < settings.QUERY_CACHE_TTL:
                self.stats.cache_hits += 1
                return result
            else:
                # Remove expired entry
                del self._query_cache[cache_key]
        return None

    def _save_to_cache(self, cache_key: str, result: GraphRAGResult):
        """Save result to cache."""
        if settings.ENABLE_QUERY_CACHE:
            self._query_cache[cache_key] = (result, time.time())
            self.stats.cache_misses += 1

    def close(self):
        """Close Neo4j driver connection."""
        if self.neo4j_driver:
            self.neo4j_driver.close()

    def get_graph_context(
        self,
        query: GraphRAGQuery
    ) -> Dict[str, Any]:
        """
        Retrieve relevant context from the knowledge graph based on the natural language query.

        This is a simplified implementation that:
        1. Extracts entities from the query using basic NLP
        2. Finds related nodes in the graph
        3. Retrieves paths between related nodes
        4. Returns structured context for LLM processing

        In a production system, you would use more sophisticated NLP and embedding-based retrieval.
        """
        start_time = time.time()

        # Check cache first
        cache_key = self._get_cache_key(query)
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            return {
                "query": query,
                "context": cached_result,
                "from_cache": True,
                "query_time_ms": (time.time() - start_time) * 1000
            }

        try:
            with self.neo4j_driver.session() as session:
                # Ponytail: Primary: Vector search using full query, Fallback: Keyword search
                # Embed the full query (better than extracting terms which misses lowercase entities)
                query_embedding = self.embedder.embed(query.query).tolist()
                similar_clusters = self.resolution_repo.find_similar_clusters(
                    embedding=query_embedding,
                    threshold=settings.SIMILARITY_THRESHOLD,
                    top_k=settings.TOP_K_RESULTS
                )
                logger.info(f"Vector search returned {len(similar_clusters)} clusters for query '{query.query}'")

                if similar_clusters:
                    # Deduplicate by node_id
                    nodes_map = {c[0]: c[1] for c in similar_clusters}
                    matching_nodes = [{"node_id": nid, "canonical_name": name} for nid, name in nodes_map.items()]
                else:
                    # Fallback to simple keyword extraction if vector search fails
                    query_terms = self._extract_query_terms(query.query)

                    # Detect intent
                    entity_type = None
                    query_lower = query.query.lower()
                    if any(w in query_lower for w in ["who", "person", "man", "woman"]):
                        entity_type = "PERSON"
                    elif any(w in query_lower for w in ["where", "location", "place"]):
                        entity_type = "LOCATION"
                    elif any(w in query_lower for w in ["organization", "org", "company"]):
                        entity_type = "ORGANIZATION"
                    elif any(w in query_lower for w in ["vehicle", "car", "truck"]):
                        entity_type = "VEHICLE"

                    # If intent detected, clear keyword terms to avoid restrictive matching if intent is broad
                    if entity_type and len(query_terms) <= 1:
                        query_terms = []

                    matching_nodes = self._find_matching_nodes(
                        session,
                        query_terms,
                        query.run_id,
                        query.include_predictions,
                        entity_type=entity_type
                    )

                logger.info(f"Retrieved {len(matching_nodes)} matching nodes for query: {query.query}")

                # Get paths between matching nodes
                paths = self._find_paths_between_nodes(
                    session,
                    matching_nodes,
                    query.run_id,
                    query.include_predictions,
                    max_length=settings.MAX_PATH_LENGTH
                )

                logger.info(f"Found {len(paths)} paths between matching nodes")

                # Get detailed node information
                node_details = self._get_node_details(
                    session,
                    [n["node_id"] for n in matching_nodes],
                    query.run_id,
                    query.include_predictions
                )

                logger.info(f"Found {len(node_details)} node details")

                # Generate natural language answer using LLM (simplified)
                answer, confidence = self._generate_answer(
                    query.query,
                    node_details,
                    paths
                )

                # Create result
                result = GraphRAGResult(
                    answer=answer,
                    confidence=confidence,
                    supporting_evidence=self._extract_supporting_evidence(node_details),
                    related_nodes=node_details,
                    related_paths=paths,
                    query_time_ms=(time.time() - start_time) * 1000
                )

                # Save to cache
                self._save_to_cache(cache_key, result)

                # Update statistics
                self.stats.total_queries += 1
                self.stats.avg_query_time_ms = (
                    (self.stats.avg_query_time_ms * (self.stats.total_queries - 1) +
                     result.query_time_ms) / self.stats.total_queries
                )
                self.stats.last_query_time = time.strftime("%Y-%m-%d %H:%M:%S")

                return {
                    "query": query,
                    "context": result,
                    "from_cache": False,
                    "query_time_ms": result.query_time_ms
                }

        except Exception as e:
            logger.error(f"GraphRAG query failed: {e}")
            # Return a fallback result
            return {
                "query": query,
                "context": GraphRAGResult(
                    answer=f"I encountered an error while querying the knowledge graph: {str(e)}",
                    confidence=0.0,
                    supporting_evidence=[],
                    related_nodes=[],
                    related_paths=[],
                    query_time_ms=(time.time() - start_time) * 1000
                ),
                "from_cache": False,
                "query_time_ms": (time.time() - start_time) * 1000
            }

    def _extract_query_terms(self, query_text: str) -> List[str]:
        """
        Extract potential entity names from the query text.
        This is a very basic implementation - in production use proper NER.
        """
        # Simple approach: split by common words and look for capitalized phrases
        import re

        # Remove common question words
        # Remove common question words/filler
        stop_words = {
            'what', 'who', 'where', 'when', 'why', 'how', 'is', 'are', 'was', 'were',
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'about', 'like', 'as', 'it', 'its', 'they', 'them',
            'show', 'all', 'found', 'list', 'find', 'tell', 'give', 'exist', 'between'
        }

        # Extract words that look like they could be entity names
        # Look for capitalized words or phrases
        words = re.findall(r'\b[A-Z][a-zA-Z]*\b|\b[A-Z]{2,}\b', query_text)

        # Also extract quoted phrases
        quoted = re.findall(r'"([^"]*)"|\'([^\']*)\'', query_text)
        quoted_phrases = [item for sublist in quoted for item in sublist if item]

        # Combine and filter
        terms = list(set(words + quoted_phrases))
        terms = [term for term in terms if term.lower() not in stop_words and len(term) > 1]

        return terms[:10]  # Limit to prevent overly broad searches

    def _find_matching_nodes(
        self,
        session,
        query_terms: List[str],
        run_id: Optional[str],
        include_predictions: bool,
        entity_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Find nodes in the graph that match the query terms."""

        # Build components
        conditions = []
        params = {}
        if query_terms:
            term_conditions = []
            for i, term in enumerate(query_terms):
                param_name = f"term_{i}"
                term_conditions.append(f"toLower(n.canonical_name) CONTAINS toLOWER(${param_name})")
                params[param_name] = term
            conditions.append(f"({' OR '.join(term_conditions)})")

        if entity_type:
            conditions.append("n.entity_type = $entity_type")
            params["entity_type"] = entity_type

        if run_id:
            conditions.append("n.graph_id = $run_id")
            params["run_id"] = run_id

        if not include_predictions:
            conditions.append("NOT EXISTS { (n)-[r:RELATION]->() WHERE r.is_predicted = true }")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cypher = f"""
        MATCH (n:Entity)
        WHERE {where_clause}
        RETURN DISTINCT n.node_id as node_id,
                       n.canonical_name as canonical_name,
                       n.entity_type as entity_type,
                       n.confidence as confidence,
                       n.source_entity_count as source_count,
                       n.evidence_count as evidence_count
        LIMIT 20
        """

        try:
            result = session.run(cypher, **params)
            nodes = []
            for record in result:
                nodes.append(dict(record))
            logger.info(f"Node matching found {len(nodes)} nodes for terms: {query_terms}")
            return nodes
        except Exception as e:
            logger.warning(f"Node matching failed: {e}")
            return []

    def _find_paths_between_nodes(
        self,
        session,
        nodes: List[Dict[str, Any]],
        run_id: Optional[str],
        include_predictions: bool,
        max_length: int = 3
    ) -> List[List[Dict[str, Any]]]:
        """Find paths between matching nodes in the graph."""
        if len(nodes) < 2:
            return []

        paths = []
        node_ids = list(dict.fromkeys(node["node_id"] for node in nodes))

        # For each pair of nodes, find paths between them
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                source_id = node_ids[i]
                target_id = node_ids[j]

                # Explicitly skip same-node paths
                if source_id == target_id:
                    continue

                # Build run filter
                run_filter = ""
                if run_id:
                    run_filter = "AND n.graph_id = $run_id AND m.graph_id = $run_id"

                # Filter predicted relationships for shortestPath
                # Note: shortestPath does not support filtering inside []
                pred_filter = ""
                if not include_predictions:
                    pred_filter = "AND ALL(r IN relationships(path) WHERE NOT r.is_predicted)"

                cypher = f"""
                MATCH (n:Entity {{node_id: $source_id}})
                MATCH (m:Entity {{node_id: $target_id}})
                MATCH path = shortestPath((n)-[:RELATION*..{max_length}]-(m))
                WHERE length(path) <= $max_length
                {run_filter}
                {pred_filter}
                RETURN [node IN nodes(path) | {{
                    node_id: node.node_id,
                    canonical_name: node.canonical_name,
                    entity_type: node.entity_type
                }}] AS node_path,
                [rel IN relationships(path) | {{
                    predicate: rel.predicate,
                    confidence: rel.confidence,
                    is_predicted: rel.is_predicted
                }}] AS rel_path
                LIMIT 5
                """

                try:
                    result = session.run(
                        cypher,
                        source_id=source_id,
                        target_id=target_id,
                        max_length=max_length,
                        run_id=run_id
                    )

                    for record in result:
                        path_data = {
                            "nodes": record["node_path"],
                            "relationships": record["rel_path"],
                            "source": node_ids[i],
                            "target": node_ids[j]
                        }
                        paths.append(path_data)

                except Exception as e:
                    logger.warning(f"Path finding failed between {source_id} and {target_id}: {e}")

        return paths

    def _get_node_details(
        self,
        session,
        node_ids: List[str],
        run_id: Optional[str],
        include_predictions: bool
    ) -> List[Dict[str, Any]]:
        """Get detailed information for specific nodes."""
        if not node_ids:
            return []

        # Build filters
        run_filter = ""
        if run_id:
            run_filter = "AND n.graph_id = $run_id"

        pred_filter = ""
        if not include_predictions:
            pred_filter = "AND NOT EXISTS { (n)-[r:RELATION]->() WHERE r.is_predicted = true }"

        cypher = f"""
        MATCH (n:Entity)
        WHERE n.node_id IN $node_ids
        {run_filter}
        {pred_filter}
        OPTIONAL MATCH (n)-[:HAS_SOURCE_ENTITY]->(se:SourceEntity)
        WITH n, collect(DISTINCT se.entity_id) as source_ids
        OPTIONAL MATCH (n)-[:HAS_EVIDENCE]->(ev:Evidence)
        WITH n, source_ids, collect(DISTINCT ev.evidence_id) as evidence_ids
        RETURN n.node_id as node_id,
               n.canonical_name as canonical_name,
               n.entity_type as entity_type,
               n.confidence as confidence,
               n.source_entity_count as source_count,
               n.evidence_count as evidence_count,
               source_ids as source_entities,
               evidence_ids as evidence_sources
        """

        try:
            result = session.run(
                cypher,
                node_ids=node_ids,
                run_id=run_id
            )

            nodes = []
            for record in result:
                node_data = dict(record)
                node_data["source_entities"] = list(set([x for x in node_data["source_entities"] if x is not None]))
                node_data["evidence_sources"] = list(set([x for x in node_data["evidence_sources"] if x is not None]))
                nodes.append(node_data)

            return nodes
        except Exception as e:
            logger.warning(f"Node details retrieval failed: {e}")
            return []

    def _generate_answer(
        self,
        query: str,
        node_details: List[Dict[str, Any]],
        paths: List[Dict[str, Any]]
    ) -> Tuple[str, float]:
        """
        Generate a natural language answer based on the retrieved context.
        This is a simplified template-based approach.
        In production, you would use an LLM to generate the answer.
        """
        if not node_details:
            return (
                "I couldn't find any relevant information in the knowledge graph to answer your question.",
                0.1
            )

        # Simple template-based answer generation
        if len(node_details) == 1:
            node = node_details[0]
            answer = f"The entity '{node['canonical_name']}' is a {node['entity_type']} "
            answer += f"with a confidence score of {node['confidence']:.2f}. "

            if node["source_entities"]:
                answer += f"It is associated with {len(node['source_entities'])} source entities. "

            if node["evidence_sources"]:
                answer += f"It appears in {len(node['evidence_sources'])} evidence sources."

            confidence = min(0.9, 0.5 + len(node["evidence_sources"]) * 0.1)

        else:
            answer = f"I found {len(node_details)} relevant entities: "
            entity_names = [node["canonical_name"] for node in node_details[:3]]
            answer += ", ".join(entity_names)
            if len(node_details) > 3:
                answer += f" and {len(node_details) - 3} more"
            answer += ". "

            if paths:
                answer += f"There are {len(paths)} paths connecting these entities in the knowledge graph. "

            confidence = min(0.8, 0.4 + len(node_details) * 0.1 + len(paths) * 0.05)

        # Add path information if available
        if paths and len(paths) > 0:
            answer += "\n\nKey connections (Rich Path Data):"
            for i, path in enumerate(paths[:3]):  # Show top 3 paths
                node_names = [n["canonical_name"] for n in path["nodes"]]
                rel_types = [r["predicate"] for r in path["relationships"]]

                path_str = " -> ".join([
                    f"{node_names[0]} (Type: {path['nodes'][0]['entity_type']}, ID: {path['nodes'][0]['node_id']})",
                    *[f"[{rel_types[j]}] -> {node_names[j+1]} (Type: {path['nodes'][j+1]['entity_type']}, ID: {path['nodes'][j+1]['node_id']})" for j in range(len(rel_types))]
                ])
                answer += f"\n{i+1}. {path_str}"

            # Append structured details
            answer += "\n\nDetailed Connections (Triple Evidence):"
            for path in paths[:3]:
                # Collect connected triples
                connections = []
                for j in range(len(path['relationships'])):
                    conn_str = f"{path['nodes'][j]['canonical_name']} -> {path['relationships'][j]['predicate']} -> {path['nodes'][j+1]['canonical_name']}"
                    connections.append(conn_str)

                answer += f"\n- {path['source']}->{path['target']}: " + "; ".join(connections)

        return answer, min(confidence, 0.95)

    def _extract_supporting_evidence(
        self,
        node_details: List[Dict[str, Any]]
    ) -> List[str]:
        """Extract supporting evidence strings from node details."""
        evidence = []
        for node in node_details:
            for ev_id in node.get("evidence_sources", []):
                if ev_id and ev_id not in evidence:
                    evidence.append(str(ev_id))
        return evidence[:10]  # Limit evidence list

    def _classify_intent(self, query_text: str) -> Optional[str]:
        q = query_text.lower()
        if "where" in q: return "LOCATION"
        if any(x in q for x in ["when", "what time"]): return "DATE_TIME"
        if "who" in q: return "PERSON"
        if any(x in q for x in ["money", "cost"]): return "MONEY_AMOUNT"
        return None

    def query_forensically(self, query_text: str, document_id: str) -> Dict[str, Any]:
        # 1. Pre-query classification
        intent_constraint = self._classify_intent(query_text)

        # 2. Forensic search
        # Note: get_graph_context takes GraphRAGQuery object
        from agent4_graphRAG.models.schemas import GraphRAGQuery
        query = GraphRAGQuery(
            query=query_text,
            max_results=10,
            include_predictions=False
        )
        # Note: Document filtering needs full implementation in get_graph_context,
        # but for now we retrieve data.
        context_data = self.get_graph_context(query)
        context_model = context_data["context"]

        # 3. Synthesis Layer (Actual LLM Call)
        synthesis = self._synthesize_natural_answer(query_text, context_model.dict())

        # Return composite
        return {
            "answer": synthesis,
            "raw_graph": context_model.dict()
        }

    def _synthesize_natural_answer(self, query: str, context: Dict) -> str:
        # Final pass: The LLM is commanded to act as forensic analyst and hide JSON structure
        prompt = f"""You are a forensic analyst. Answer the user prompt based on the provided Knowledge Graph data.

        CRITICAL RULES:
        1. NO JSON/METADATA: Do not mention nodes, edges, Confidence Scores, or IDs.
        2. NATURAL LANGUAGE: Provide a plain, synthesized summary of facts based on the following KG data.

        User Question: {query}
        KG Data: {json.dumps(context)}
        """

        # Perform real LLM call
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{settings.NL_LLM_BASE_URL}/chat/completions",
                    json={
                        "model": settings.NL_LLM_MODEL_NAME,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                    },
                )
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"].strip()
                return f"Error from synthesis layer: {response.text}"
        except Exception as e:
            return f"Error during forensic synthesis: {str(e)}"
