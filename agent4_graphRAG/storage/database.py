"""
storage/database.py — Data access layer for Agent 4 GraphRAG
Responsibility: Query knowledge graph from Neo4j and PostgreSQL for context retrieval.
"""

import hashlib
import json
import re
import time
import httpx
from typing import List, Dict, Optional, Tuple, Any, Union
from loguru import logger
from neo4j import GraphDatabase

from agent4_graphRAG.config import settings
from agent4_graphRAG.models.schemas import (
    GraphRAGQuery,
    GraphRAGResult,
    GraphRAGStats,
    NodeDetail,
    PathDetail,
    PathRelationship,
)

# Reuse Agent 2 resolution infra for vector search
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

        # Reuse Agent 2 resolution infra
        self.embedder = BGEEmbedder()
        self.resolution_repo = ResolutionRepository()

        # Shared HTTP client for LLM synthesis (eliminates TCP/TLS handshake overhead per query)
        llm_timeout = getattr(settings, "LLM_TIMEOUT", 60.0)
        self.http_client = httpx.Client(timeout=llm_timeout)

        # In-memory cache for query results
        self._query_cache: Dict[str, Tuple[GraphRAGResult, float]] = {}

        # Statistics tracking
        self.stats = GraphRAGStats()

    def _clear_expired_cache(self):
        """Remove expired cache entries."""
        if not getattr(settings, "ENABLE_QUERY_CACHE", True):
            return

        current_time = time.time()
        ttl = getattr(settings, "QUERY_CACHE_TTL", 300)
        expired_keys = [
            key for key, (_, timestamp) in self._query_cache.items()
            if current_time - timestamp > ttl
        ]
        for key in expired_keys:
            del self._query_cache[key]

    def _get_cache_key(self, query: GraphRAGQuery) -> str:
        """Generate a cache key for the query."""
        query_str = f"{query.query}:{query.run_id}:{query.include_predictions}:{query.max_results}"
        return hashlib.md5(query_str.encode()).hexdigest()

    def _get_from_cache(self, cache_key: str) -> Optional[GraphRAGResult]:
        """Get result from cache if available and not expired."""
        if not getattr(settings, "ENABLE_QUERY_CACHE", True):
            return None

        if cache_key in self._query_cache:
            result, timestamp = self._query_cache[cache_key]
            ttl = getattr(settings, "QUERY_CACHE_TTL", 300)
            if time.time() - timestamp < ttl:
                self.stats.cache_hits += 1
                return result
            else:
                del self._query_cache[cache_key]
        return None

    def _save_to_cache(self, cache_key: str, result: GraphRAGResult):
        """Save result to cache."""
        if getattr(settings, "ENABLE_QUERY_CACHE", True):
            self._query_cache[cache_key] = (result, time.time())
            self.stats.cache_misses += 1

    def close(self):
        """Close Neo4j driver connection and persistent HTTP client."""
        if self.neo4j_driver:
            self.neo4j_driver.close()
        if hasattr(self, "http_client") and self.http_client:
            self.http_client.close()

    def get_graph_context(
        self,
        query: GraphRAGQuery
    ) -> Dict[str, Any]:
        """
        Retrieve relevant context from the knowledge graph based on the natural language query.
        """
        start_time = time.time()

        # Evict expired cache entries before checking cache
        self._clear_expired_cache()

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
                # 1. Intent & term extraction (incorporating regex identifiers from Agent 1)
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

                # 4. Get paths and direct neighborhood relationships using batched Cypher execution
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
                        if isinstance(n, dict) and n.get("node_id"):
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

                # Construct strongly typed Pydantic models
                typed_nodes = [
                    NodeDetail(
                        node_id=n["node_id"],
                        canonical_name=n.get("canonical_name", "UNKNOWN"),
                        entity_type=n.get("entity_type", "UNKNOWN"),
                        confidence=n.get("confidence", 1.0),
                        source_entities=n.get("source_entities", []),
                        evidence_sources=n.get("evidence_sources", [])
                    )
                    for n in node_details
                ]

                typed_paths = []
                for p in paths:
                    path_nodes = [
                        NodeDetail(
                            node_id=pn.get("node_id", ""),
                            canonical_name=pn.get("canonical_name", "UNKNOWN"),
                            entity_type=pn.get("entity_type", "UNKNOWN"),
                            confidence=pn.get("confidence", 1.0),
                            source_entities=pn.get("source_entities", []),
                            evidence_sources=pn.get("evidence_sources", [])
                        )
                        for pn in p.get("nodes", [])
                    ]
                    path_rels = [
                        PathRelationship(
                            predicate=pr.get("predicate", "CONNECTED_TO"),
                            confidence=pr.get("confidence", 1.0),
                            is_predicted=pr.get("is_predicted", False)
                        )
                        for pr in p.get("relationships", [])
                    ]
                    typed_paths.append(
                        PathDetail(
                            source=p.get("source", ""),
                            target=p.get("target", ""),
                            nodes=path_nodes,
                            relationships=path_rels
                        )
                    )

                # Create result
                result = GraphRAGResult(
                    answer=answer,
                    confidence=confidence,
                    supporting_evidence=self._extract_supporting_evidence(node_details),
                    related_nodes=typed_nodes,
                    related_paths=typed_paths,
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
        Extract entity terms, alphanumeric identifiers, and structured codes using regex patterns.
        Combines Agent 1 deterministic patterns with token extraction.
        """
        terms: List[str] = []

        # 1. Regex patterns from Agent 1 to extract identifiers (FIR, Transaction IDs, Legal Sections, etc.)
        entity_patterns = [
            r"\b(?:RTGS|NEFT|IMPS|TXN|REF|DEX)[\:\-\_\s]?[A-Za-z0-9]{6,22}\b",  # Transaction IDs
            r"\b(?:FIR[\_\s]*(?:No\.|Number|[\#\:\_])?\s*)?\d{3,6}\/\d{2,4}\b|\bFIR[\_\s]*\d{3,6}[\_\s]*\d{2,4}\b",  # FIR numbers
            r"\b(?:IPC|IT Act|Section|Sec\.|Art\.|Article)\s+(?:Section\s+)?\d+[A-Za-z]?\b",  # Legal sections
            r"\b(?:\+?91[\-\s]?)?[6-9]\d{9}\b",  # Phone numbers
            r"(?:\$|€|£|₹|Rs\.?\s?)\s?[\d,]+(?:\.\d{1,2})?(?:\s*(?:lakhs?|crores?|million|billion|k|m|b))?\b",  # Money
            r"\b[A-Z]{2}[\-\s]?\d{2}[\-\s]?[A-Z]{1,3}[\-\s]?\d{4}\b",  # Vehicles
            r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",  # IP address
        ]

        for pattern in entity_patterns:
            matches = re.findall(pattern, query_text, re.IGNORECASE)
            for m in matches:
                clean_m = re.sub(r"\s+", " ", m).strip()
                if clean_m and clean_m not in terms:
                    terms.append(clean_m)

        # 2. General token extraction for capitalized phrases and alphanumeric codes
        stop_words = {
            'what', 'who', 'where', 'when', 'why', 'how', 'is', 'are', 'was', 'were',
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'about', 'like', 'as', 'it', 'its', 'they', 'them',
            'show', 'all', 'found', 'list', 'find', 'tell', 'give', 'exist', 'between'
        }

        tokens = re.findall(r'\b[A-Za-z0-9_\-]{3,}\b', query_text)
        for t in tokens:
            if t.lower() not in stop_words and not t.isdigit() and t not in terms:
                terms.append(t)

        # 3. Extract quoted phrases
        quoted = re.findall(r'"([^"]*)"|\'([^\']*)\'', query_text)
        for sublist in quoted:
            for item in sublist:
                if item and item not in terms:
                    terms.append(item)

        return terms[:10]

    def _find_matching_nodes(
        self,
        session,
        query_terms: List[str],
        run_id: Optional[str],
        include_predictions: bool,
        entity_type: Optional[Union[str, List[str]]] = None
    ) -> List[Dict[str, Any]]:
        """Find nodes in the graph that match the query terms."""

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

    def _find_paths_between_nodes(
        self,
        session,
        nodes: List[Dict[str, Any]],
        run_id: Optional[str],
        include_predictions: bool,
        max_length: int = 3
    ) -> List[Dict[str, Any]]:
        """Find paths and direct relationships between matching nodes in the graph using batched Cypher execution."""
        if not nodes:
            return []

        paths = []
        node_ids = list(dict.fromkeys(node["node_id"] for node in nodes))

        # 1. Multi-node shortest paths (Batched Cypher query via UNWIND to avoid O(N^2) roundtrips)
        if len(node_ids) >= 2:
            pairs = []
            for i in range(len(node_ids)):
                for j in range(i + 1, len(node_ids)):
                    if node_ids[i] != node_ids[j]:
                        pairs.append({"source": node_ids[i], "target": node_ids[j]})

            if pairs:
                run_filter = "AND n.graph_id = $run_id AND m.graph_id = $run_id" if run_id else ""
                pred_filter = "AND ALL(r IN relationships(path) WHERE NOT coalesce(r.is_predicted, false))" if not include_predictions else ""

                cypher_batched = f"""
                UNWIND $pairs AS pair
                MATCH (n:Entity {{node_id: pair.source}})
                MATCH (m:Entity {{node_id: pair.target}})
                MATCH path = shortestPath((n)-[*..{max_length}]-(m))
                WHERE length(path) <= $max_length
                {run_filter}
                {pred_filter}
                RETURN pair.source AS source_id, pair.target AS target_id,
                       [node IN nodes(path) | {{
                           node_id: node.node_id,
                           canonical_name: node.canonical_name,
                           entity_type: node.entity_type
                       }}] AS node_path,
                       [rel IN relationships(path) | {{
                           predicate: type(rel),
                           confidence: coalesce(rel.confidence, 1.0),
                           is_predicted: coalesce(rel.is_predicted, false)
                       }}] AS rel_path
                LIMIT 20
                """

                try:
                    result = session.run(
                        cypher_batched,
                        pairs=pairs,
                        max_length=max_length,
                        run_id=run_id
                    )

                    for record in result:
                        paths.append({
                            "source": record["source_id"],
                            "target": record["target_id"],
                            "nodes": record["node_path"],
                            "relationships": record["rel_path"]
                        })

                except Exception as e:
                    logger.warning(f"Batched path finding failed: {e}")

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
                   type(r) AS predicate, coalesce(r.confidence, 1.0) AS confidence, coalesce(r.is_predicted, false) AS is_predicted,
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
                        pred = rel.get("predicate", "CONNECTED_TO") if isinstance(rel, dict) else getattr(rel, "predicate", "CONNECTED_TO")
                        src_id = src.get("node_id") if isinstance(src, dict) else getattr(src, "node_id")
                        tgt_id = tgt.get("node_id") if isinstance(tgt, dict) else getattr(tgt, "node_id")
                        src_name = src.get("canonical_name") if isinstance(src, dict) else getattr(src, "canonical_name")
                        tgt_name = tgt.get("canonical_name") if isinstance(tgt, dict) else getattr(tgt, "canonical_name")

                        triple_key = (src_id, pred, tgt_id)
                        if triple_key not in seen_triples:
                            seen_triples.add(triple_key)
                            lines.append(
                                f"  • [{src_name} (ID: {src_id})] "
                                f"--[{pred}]--> [{tgt_name} (ID: {tgt_id})]"
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
        return evidence[:10]

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
        intent_constraint = self._classify_intent(query_text)

        query = GraphRAGQuery(
            query=query_text,
            max_results=15,
            include_predictions=False
        )
        context_data = self.get_graph_context(query)
        context_model: GraphRAGResult = context_data["context"]

        structured_summary = context_model.answer

        context_dict = context_model.model_dump() if hasattr(context_model, "model_dump") else context_model.dict()

        synthesis = self._synthesize_natural_answer(query_text, context_dict, structured_summary)

        return {
            "answer": synthesis,
            "structured_connections": structured_summary,
            "raw_graph": context_dict
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
            # Reusing persistent HTTP client to eliminate TCP/TLS handshake overhead
            response = self.http_client.post(
                f"{settings.NL_LLM_BASE_URL}/chat/completions",
                json={
                    "model": settings.NL_LLM_MODEL_NAME,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                },
            )
            if response.status_code == 200:
                llm_answer = response.json()["choices"][0]["message"]["content"].strip()
                if llm_answer and not llm_answer.startswith("This is a JSON object") and "properties, including:" not in llm_answer:
                    return llm_answer
        except Exception as e:
            logger.warning(f"LLM synthesis failed: {e}")

        return self._generate_forensic_answer(query, structured_summary)

    def _generate_forensic_answer(self, query: str, structured_summary: str) -> str:
        """Generate a natural language answer from the structured summary without hardcoded domain surnames."""
        if not structured_summary or "Found 0 relevant entities" in structured_summary:
            return "I couldn't find any relevant information in the knowledge graph to answer your question."

        lines = structured_summary.strip().split('\n')

        entities = []
        connections = []
        in_entities = False
        in_connections = False

        for line in lines:
            if line.startswith("Found ") and "relevant entities" in line:
                in_entities = True
                continue
            elif line.startswith("Connected Graph Triples & Relationships:"):
                in_entities = False
                in_connections = True
                continue
            elif in_entities and line.strip().startswith("•"):
                if "(" in line and ") -->" not in line:
                    entity_part = line.split("(")[0].strip()
                    if entity_part.startswith("•"):
                        entity_part = entity_part[1:].strip()
                    entities.append(entity_part)
            elif in_connections and line.strip().startswith("•"):
                connections.append(line.strip())

        query_lower = query.lower()

        if any(w in query_lower for w in ["who", "person", "people", "individual", "suspect"]):
            if entities:
                if len(entities) == 1:
                    return f"The FIR documents mention the following individual: {entities[0]}."
                else:
                    entities_str = ", ".join(entities[:-1]) + f", and {entities[-1]}"
                    return f"The FIR documents mention the following individuals: {entities_str}."

        elif any(w in query_lower for w in ["relationship", "connection", "connected"]):
            if connections:
                cleaned_connections = []
                for conn in connections:
                    match = re.match(r'\[([^]]+)\s*\(ID:[^]]+\)\]\s*--\[([^]]+)\]-->\s*\[([^]]+)\s*\(ID:[^]]+\)\]', conn)
                    if match:
                        src, rel, tgt = match.groups()
                        cleaned_connections.append(f"{src} {rel} {tgt}")
                    else:
                        cleaned_connections.append(conn)

                if len(cleaned_connections) == 1:
                    return f"The following relationship exists: {cleaned_connections[0]}."
                else:
                    connections_str = "; ".join(cleaned_connections[:-1]) + f", and {cleaned_connections[-1]}"
                    return f"The following relationships exist: {connections_str}."

        return f"Based on the knowledge graph analysis: {structured_summary}"