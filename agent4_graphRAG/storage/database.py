"""
storage/database.py — Data access layer for Agent 4 GraphRAG
Responsibility: Query knowledge graph from Neo4j and PostgreSQL for context retrieval.
"""

import hashlib
import json
import time
import httpx
from typing import List, Dict, Optional, Tuple, Any, Union
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
                # 1. Intent & term extraction
                intent_type = self._classify_intent(query.query)
                query_terms = self._extract_query_terms(query.query)

                # 2. Vector search using BGE-m3 and pgvector
                query_embedding = self.embedder.embed(query.query).tolist()
                similar_clusters = self.resolution_repo.find_similar_clusters(
                    embedding=query_embedding,
                    entity_type=intent_type,
                    threshold=settings.SIMILARITY_THRESHOLD,
                    top_k=settings.TOP_K_RESULTS
                )

                if not similar_clusters and intent_type:
                    similar_clusters = self.resolution_repo.find_similar_clusters(
                        embedding=query_embedding,
                        threshold=settings.SIMILARITY_THRESHOLD,
                        top_k=settings.TOP_K_RESULTS
                    )

                logger.info(f"Vector search returned {len(similar_clusters)} clusters for query '{query.query}'")

                matching_nodes = []
                if similar_clusters:
                    nodes_map = {c[0]: c[1] for c in similar_clusters}
                    matching_nodes = [{"node_id": nid, "canonical_name": name} for nid, name in nodes_map.items()]

                # 3. Keyword / Intent search fallback & complement
                if len(matching_nodes) < 3:
                    keyword_nodes = self._find_matching_nodes(
                        session,
                        query_terms,
                        query.run_id,
                        query.include_predictions,
                        entity_type=intent_type
                    )
                    existing_ids = {n["node_id"] for n in matching_nodes}
                    for kn in keyword_nodes:
                        if kn["node_id"] not in existing_ids:
                            matching_nodes.append(kn)
                            existing_ids.add(kn["node_id"])

                # If still empty and intent exists, fetch nodes of that entity_type
                if not matching_nodes and intent_type:
                    matching_nodes = self._find_matching_nodes(
                        session,
                        [],
                        query.run_id,
                        query.include_predictions,
                        entity_type=intent_type
                    )

                # If still empty for broad query, fetch top entities
                if not matching_nodes:
                    matching_nodes = self._find_matching_nodes(
                        session,
                        [],
                        query.run_id,
                        query.include_predictions,
                        entity_type=None
                    )

                logger.info(f"Retrieved {len(matching_nodes)} matching nodes for query: {query.query}")

                # 4. Get paths and direct neighborhood relationships
                paths = self._find_paths_between_nodes(
                    session,
                    matching_nodes,
                    query.run_id,
                    query.include_predictions,
                    max_length=settings.MAX_PATH_LENGTH
                )

                logger.info(f"Found {len(paths)} paths/triples between matching nodes")

                # Collect all node IDs involved in matches and paths
                all_node_ids = set(n["node_id"] for n in matching_nodes)
                for p in paths:
                    for n in p.get("nodes", []):
                        if n.get("node_id"):
                            all_node_ids.add(n["node_id"])

                # 5. Get detailed node information with cluster IDs and metadata
                node_details = self._get_node_details(
                    session,
                    list(all_node_ids),
                    query.run_id,
                    query.include_predictions
                )

                logger.info(f"Found {len(node_details)} node details")

                # 6. Generate answer
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
        entity_type: Optional[Union[str, List[str]]] = None
    ) -> List[Dict[str, Any]]:
        """Find nodes in the graph that match the query terms."""

        # Build components
        conditions = []
        params = {}
        if query_terms:
            term_conditions = []
            for i, term in enumerate(query_terms):
                param_name = f"term_{i}"
                term_conditions.append(f"toLower(n.canonical_name) CONTAINS toLower(${param_name})")
                params[param_name] = term
            conditions.append(f"({' OR '.join(term_conditions)})")

        if entity_type:
            if isinstance(entity_type, list):
                conditions.append("n.entity_type IN $entity_types")
                params["entity_types"] = entity_type
            else:
                conditions.append("n.entity_type = $entity_type")
                params["entity_type"] = entity_type

        if run_id:
            conditions.append("n.graph_id = $run_id")
            params["run_id"] = run_id

        if not include_predictions:
            conditions.append("NOT EXISTS { (n)-[r]->() WHERE r.is_predicted = true }")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cypher = f"""
        MATCH (n:Entity)
        WHERE {where_clause}
        RETURN DISTINCT n.node_id as node_id,
                       n.canonical_name as canonical_name,
                       n.entity_type as entity_type,
                       n.confidence as confidence,
                       coalesce(n.source_doc_ids, []) as source_entities,
                       coalesce(n.evidence_ids, []) as evidence_sources
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
            logger.warning(f"Node matching failed: {e}")
            return []

    def _find_paths_between_nodes(
        self,
        session,
        nodes: List[Dict[str, Any]],
        run_id: Optional[str],
        include_predictions: bool,
        max_length: int = 3
    ) -> List[Dict[str, Any]]:
        """Find paths and direct relationships between matching nodes in the graph."""
        if not nodes:
            return []

        paths = []
        node_ids = list(dict.fromkeys(node["node_id"] for node in nodes))

        # 1. Multi-node shortest paths
        if len(node_ids) >= 2:
            for i in range(len(node_ids)):
                for j in range(i + 1, len(node_ids)):
                    source_id = node_ids[i]
                    target_id = node_ids[j]

                    if source_id == target_id:
                        continue

                    run_filter = ""
                    if run_id:
                        run_filter = "AND n.graph_id = $run_id AND m.graph_id = $run_id"

                    pred_filter = ""
                    if not include_predictions:
                        pred_filter = "AND ALL(r IN relationships(path) WHERE NOT r.is_predicted)"

                    cypher = f"""
                    MATCH (n:Entity {{node_id: $source_id}})
                    MATCH (m:Entity {{node_id: $target_id}})
                    MATCH path = shortestPath((n)-[*..{max_length}]-(m))
                    WHERE length(path) <= $max_length
                    {run_filter}
                    {pred_filter}
                    RETURN [node IN nodes(path) | {{
                        node_id: node.node_id,
                        canonical_name: node.canonical_name,
                        entity_type: node.entity_type
                    }}] AS node_path,
                    [rel IN relationships(path) | {{
                        predicate: type(rel),
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

        # 2. Neighborhood 1-hop expansion (vital for single entity queries or disconnected nodes)
        if len(paths) < 3 and node_ids:
            run_filter = "AND n.graph_id = $run_id AND m.graph_id = $run_id" if run_id else ""
            pred_filter = "AND (r.is_predicted IS NULL OR r.is_predicted = false)" if not include_predictions else ""

            cypher_1hop = f"""
            MATCH (n:Entity)-[r]-(m:Entity)
            WHERE n.node_id IN $node_ids
            {run_filter}
            {pred_filter}
            RETURN n.node_id AS s_id, n.canonical_name AS s_name, n.entity_type AS s_type,
                   type(r) AS predicate, r.confidence AS confidence, r.is_predicted AS is_predicted,
                   m.node_id AS t_id, m.canonical_name AS t_name, m.entity_type AS t_type,
                   startNode(r) = n AS is_outgoing
            LIMIT 25
            """
            try:
                result_1hop = session.run(cypher_1hop, node_ids=node_ids, run_id=run_id)
                seen_edges = set()
                for rec in result_1hop:
                    s_id = rec["s_id"] if rec["is_outgoing"] else rec["t_id"]
                    t_id = rec["t_id"] if rec["is_outgoing"] else rec["s_id"]
                    s_name = rec["s_name"] if rec["is_outgoing"] else rec["t_name"]
                    t_name = rec["t_name"] if rec["is_outgoing"] else rec["s_name"]
                    s_type = rec["s_type"] if rec["is_outgoing"] else rec["t_type"]
                    t_type = rec["t_type"] if rec["is_outgoing"] else rec["s_type"]
                    predicate = rec["predicate"]

                    edge_sig = (s_id, predicate, t_id)
                    if edge_sig not in seen_edges:
                        seen_edges.add(edge_sig)
                        paths.append({
                            "source": s_id,
                            "target": t_id,
                            "nodes": [
                                {"node_id": s_id, "canonical_name": s_name, "entity_type": s_type},
                                {"node_id": t_id, "canonical_name": t_name, "entity_type": t_type}
                            ],
                            "relationships": [
                                {"predicate": predicate, "confidence": rec["confidence"], "is_predicted": rec["is_predicted"]}
                            ]
                        })
            except Exception as e:
                logger.warning(f"1-hop neighborhood retrieval failed: {e}")

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

        cypher = f"""
        MATCH (n:Entity)
        WHERE n.node_id IN $node_ids
        {run_filter}
        RETURN n.node_id as node_id,
               n.canonical_name as canonical_name,
               n.entity_type as entity_type,
               n.confidence as confidence,
               coalesce(n.source_doc_ids, []) as source_entities,
               coalesce(n.evidence_ids, []) as evidence_sources
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
                node_data["source_entities"] = list(set([x for x in node_data.get("source_entities", []) if x is not None]))
                node_data["evidence_sources"] = list(set([x for x in node_data.get("evidence_sources", []) if x is not None]))
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
        Generate a detailed natural language summary and connection report
        including cluster IDs, node IDs, and all connected triples.
        """
        if not node_details:
            return (
                "I couldn't find any relevant information in the knowledge graph to answer your question.",
                0.1
            )

        lines = []

        # 1. Entity summary with Cluster / Node IDs
        lines.append(f"Found {len(node_details)} relevant entities in the Knowledge Graph:")
        for node in node_details:
            cid = node.get("node_id", "N/A")
            etype = node.get("entity_type", "UNKNOWN")
            cname = node.get("canonical_name", "UNKNOWN")
            conf = node.get("confidence", 1.0)
            lines.append(f"  • {cname} (Type: {etype}, Node/Cluster ID: {cid}, Confidence: {conf:.2f})")

        # 2. Connection and Triple Evidence
        if paths:
            lines.append("\nConnected Graph Triples & Relationships:")
            seen_triples = set()
            for path in paths:
                p_nodes = path.get("nodes", [])
                p_rels = path.get("relationships", [])
                for idx, rel in enumerate(p_rels):
                    if idx < len(p_nodes) - 1:
                        src = p_nodes[idx]
                        tgt = p_nodes[idx + 1]
                        pred = rel.get("predicate", "CONNECTED_TO")
                        triple_key = (src.get("node_id"), pred, tgt.get("node_id"))
                        if triple_key not in seen_triples:
                            seen_triples.add(triple_key)
                            lines.append(
                                f"  • [{src.get('canonical_name')} (ID: {src.get('node_id')})] "
                                f"--[{pred}]--> [{tgt.get('canonical_name')} (ID: {tgt.get('node_id')})]"
                            )

        confidence = min(0.95, 0.4 + len(node_details) * 0.05 + len(paths) * 0.05)
        return "\n".join(lines), confidence

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

    def _classify_intent(self, query_text: str) -> Optional[Union[str, List[str]]]:
        q = query_text.lower()
        if "where" in q or "location" in q or "place" in q:
            return "LOCATION"
        if any(x in q for x in ["when", "what time", "date", "time", "hour"]):
            return "DATE_TIME"
        if "who" in q or "person" in q or "people" in q or "suspect" in q:
            return ["PERSON", "ORGANIZATION"]
        if any(x in q for x in ["organization", "company", "bank", "exchange", "syndicate"]):
            return "ORGANIZATION"
        if any(x in q for x in ["money", "cost", "amount", "extort", "profit", "transfer", "financial", "rupees", "rs."]):
            return ["MONEY_AMOUNT", "TRANSACTION_ID"]
        if any(x in q for x in ["vehicle", "car", "bike", "truck"]):
            return "IDENTIFIER"
        if any(x in q for x in ["section", "act", "ipc", "law", "charge"]):
            return "LEGAL_SECTION"
        return None

    def query_forensically(self, query_text: str, document_id: str) -> Dict[str, Any]:
        # 1. Pre-query classification
        intent_constraint = self._classify_intent(query_text)

        # 2. Forensic search
        from agent4_graphRAG.models.schemas import GraphRAGQuery
        query = GraphRAGQuery(
            query=query_text,
            max_results=15,
            include_predictions=False
        )
        context_data = self.get_graph_context(query)
        context_model = context_data["context"]

        # 3. Generate structured connections
        structured_summary = context_model.answer

        # 4. Synthesis Layer (Forensic LLM Analysis)
        synthesis = self._synthesize_natural_answer(query_text, context_model.dict(), structured_summary)

        # Return composite
        return {
            "answer": synthesis,
            "structured_connections": structured_summary,
            "raw_graph": context_model.dict()
        }

    def _synthesize_natural_answer(self, query: str, context: Dict, structured_summary: str = "") -> str:
        prompt = f"""You are a senior forensic data extraction and intelligence analyst investigating First Information Reports (FIRs).
Analyze the provided Knowledge Graph data to provide a comprehensive, rigorous forensic investigative report answering the user's query.

CRITICAL INSTRUCTIONS:
1. EXECUTIVE SUMMARY: Direct, clear narrative explaining the facts answering the question.
2. DETAILED ENTITY CONNECTIONS: Detail all mentioned entities, their roles, and explicitly explain how they are connected to each other (e.g. fund transfers, cyber intrusions, orchestrations, employment, conspiracies).
3. TRIPLE & PROVENANCE CITATIONS: Include the specific Knowledge Graph triples [Subject] -> [Predicate] -> [Object] and mention the relevant Database Node/Cluster IDs (e.g., CLU-..., FIR_1102_2026) for auditability.
4. ZERO HALLUCINATION: Only use facts, dates, amounts, locations, and relationships present in the provided KG context.

User Query: {query}

Knowledge Graph Triples & Structured Context:
{structured_summary}

Raw Graph Context:
{json.dumps(context, indent=2)}
"""

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
                return f"{structured_summary}\n\n(Synthesis status: {response.status_code})"
        except Exception as e:
            return f"{structured_summary}\n\n(Forensic synthesis note: {str(e)})"
