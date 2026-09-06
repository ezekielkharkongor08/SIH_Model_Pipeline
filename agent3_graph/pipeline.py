"""
pipeline.py — Main pipeline for Agent 3 Knowledge Graph Builder + Link Prediction
Responsibility: Build knowledge graph from Agent 1 & 2 data, optionally predict missing links.
"""

import time
import json
from typing import Optional, Dict, Any
from loguru import logger

from agent3_graph.config import settings
from agent3_graph.storage.database import GraphRepository
from agent3_graph.models.schemas import KnowledgeGraph
from agent3_graph.exporters.neo4j_exporter import Neo4jExporter
from agent3_graph.exporters.networkx_exporter import NetworkxExporter


class KnowledgeGraphPipeline:
    """Orchestrator for building and exporting knowledge graphs with optional link prediction."""

    def __init__(self):
        self.repository = GraphRepository()
        self.neo4j_exporter = Neo4jExporter()
        self.networkx_exporter = NetworkxExporter()

    def build_graph(
        self,
        run_id: str,
        include_predictions: bool = None
    ) -> KnowledgeGraph:
        """
        Build a knowledge graph from Agent 1 & 2 data for a given resolution run.

        Args:
            run_id: Agent 2 resolution run ID
            include_predictions: Override config setting for link prediction

        Returns:
            KnowledgeGraph with nodes, edges, and optionally predicted links
        """
        start_time = time.time()

        # Use config default if not specified
        if include_predictions is None:
            include_predictions = settings.INCLUDE_PREDICTIONS

        logger.info(
            f"Building knowledge graph for resolution run: {run_id} "
            f"(include_predictions={include_predictions})"
        )

        try:
            # Build the base knowledge graph
            knowledge_graph = self.repository.build_knowledge_graph(run_id)

            # Add predicted links if enabled
            if include_predictions:
                logger.info("Running link prediction...")
                predicted_edges = self.repository.predict_links(
                    run_id=run_id,
                    existing_edges=knowledge_graph.edges,
                    threshold=settings.LINK_PREDICTION_THRESHOLD
                )

                # Filter by minimum confidence
                predicted_edges = [
                    edge for edge in predicted_edges
                    if edge.confidence >= settings.PREDICTION_MIN_CONFIDENCE
                ]

                if predicted_edges:
                    original_edge_count = len(knowledge_graph.edges)
                    knowledge_graph.edges.extend(predicted_edges)
                    knowledge_graph.edge_count = len(knowledge_graph.edges)

                    logger.info(
                        f"Added {len(predicted_edges)} predicted links "
                        f"(total edges: {original_edge_count} → {knowledge_graph.edge_count})"
                    )

            execution_time = round((time.time() - start_time) * 1000, 2)

            logger.info(
                f"Knowledge graph built successfully: {knowledge_graph.graph_id} "
                f"({knowledge_graph.node_count} nodes, {knowledge_graph.edge_count} edges) "
                f"in {execution_time}ms"
            )

            return knowledge_graph

        except Exception as e:
            logger.error(f"Failed to build knowledge graph for run {run_id}: {e}")
            raise

    def export_to_neo4j(self, graph: KnowledgeGraph) -> bool:
        """Export knowledge graph to Neo4j database."""
        try:
            success = self.neo4j_exporter.export_graph(graph)
            if success:
                logger.info(f"Exported graph {graph.graph_id} to Neo4j successfully")
            else:
                logger.warning(f"Failed to export graph {graph.graph_id} to Neo4j")
            return success
        except Exception as e:
            logger.error(f"Neo4j export failed for graph {graph.graph_id}: {e}")
            return False

    def export_to_networkx(self, graph: KnowledgeGraph) -> Optional[Any]:
        """Export knowledge graph to NetworkX graph object."""
        try:
            nx_graph = self.networkx_exporter.export_graph(graph)
            logger.info(f"Exported graph {graph.graph_id} to NetworkX successfully")
            return nx_graph
        except Exception as e:
            logger.error(f"NetworkX export failed for graph {graph.graph_id}: {e}")
            return None

    def export_as_json(self, graph: KnowledgeGraph) -> str:
        """Export knowledge graph as JSON string."""
        try:
            json_str = graph.json(indent=2)
            logger.info(f"Exported graph {graph.graph_id} as JSON successfully")
            return json_str
        except Exception as e:
            logger.error(f"JSON export failed for graph {graph.graph_id}: {e}")
            raise

    def build_and_export(
        self,
        run_id: str,
        export_formats: list[str] = ["json"],
        include_predictions: bool = None
    ) -> Dict[str, Any]:
        """
        Build a knowledge graph and export to specified formats.

        Args:
            run_id: Agent 2 resolution run ID
            export_formats: List of formats to export to ["json", "neo4j", "networkx"]
            include_predictions: Override config setting for link prediction

        Returns:
            Dict containing graph metadata and export results
        """
        result = {
            "run_id": run_id,
            "graph_id": None,
            "exports": {},
            "statistics": {},
        }

        try:
            # Build the graph (with optional predictions)
            graph = self.build_graph(run_id, include_predictions=include_predictions)
            result["graph_id"] = graph.graph_id

            # Count predicted vs real edges
            predicted_count = sum(1 for edge in graph.edges if edge.is_predicted)
            real_count = graph.edge_count - predicted_count

            result["statistics"] = {
                "node_count": graph.node_count,
                "edge_count": graph.edge_count,
                "real_edges": real_count,
                "predicted_edges": predicted_count,
                "timestamp": graph.created_at,
            }

            # Export to requested formats
            for fmt in export_formats:
                if fmt == "json":
                    result["exports"]["json"] = self.export_as_json(graph)
                elif fmt == "neo4j":
                    result["exports"]["neo4j"] = self.export_to_neo4j(graph)
                elif fmt == "networkx":
                    nx_graph = self.export_to_networkx(graph)
                    if nx_graph:
                        result["exports"]["networkx"] = "success"
                else:
                    logger.warning(f"Unknown export format: {fmt}")

            logger.info(f"Build and export completed for run {run_id}")
            return result

        except Exception as e:
            logger.error(f"Build and export failed for run {run_id}: {e}")
            raise