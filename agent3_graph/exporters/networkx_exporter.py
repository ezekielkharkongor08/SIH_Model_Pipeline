"""
exporters/networkx_exporter.py — Export knowledge graph to NetworkX format.
"""

from typing import Optional, Dict, Any
from loguru import logger
import networkx as nx

from agent3_graph.models.schemas import KnowledgeGraph


class NetworkxExporter:
    """Export knowledge graph to NetworkX format for analysis."""

    def export_graph(self, graph: KnowledgeGraph) -> nx.DiGraph:
        """
        Export knowledge graph to NetworkX directed graph.

        Returns:
            NetworkX DiGraph object with nodes and edges.
        """
        try:
            # Create directed graph
            G = nx.DiGraph()

            # Add graph metadata
            G.graph["graph_id"] = graph.graph_id
            G.graph["run_id"] = graph.run_id
            G.graph["node_count"] = graph.node_count
            G.graph["edge_count"] = graph.edge_count
            G.graph["created_at"] = graph.created_at

            # Add nodes with attributes
            for node in graph.nodes:
                G.add_node(
                    node.node_id,
                    canonical_name=node.canonical_name,
                    entity_type=node.entity_type,
                    confidence=node.confidence,
                    source_entity_count=len(node.source_entities),
                    evidence_count=len(node.evidence_sources),
                    source_entities=node.source_entities,
                    evidence_sources=node.evidence_sources,
                )

            # Add edges with attributes
            for edge in graph.edges:
                G.add_edge(
                    edge.source_node,
                    edge.target_node,
                    edge_id=edge.edge_id,
                    predicate=edge.predicate,
                    confidence=edge.confidence,
                    original_triple_count=len(edge.original_triples),
                    original_triples=edge.original_triples,
                    temporal=edge.temporal,
                    spatial=edge.spatial,
                )

            logger.info(
                f"Exported graph '{graph.graph_id}' to NetworkX: "
                f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges"
            )

            return G

        except Exception as e:
            logger.error(f"NetworkX export failed for graph {graph.graph_id}: {e}")
            raise

    def compute_statistics(self, G: nx.DiGraph) -> Dict[str, Any]:
        """Compute graph statistics using NetworkX algorithms."""
        stats = {
            "basic": {
                "nodes": G.number_of_nodes(),
                "edges": G.number_of_edges(),
                "density": nx.density(G),
                "is_directed": G.is_directed(),
            },
            "connectivity": {},
            "centrality": {},
            "components": {},
        }

        try:
            # Connectivity metrics
            if nx.is_weakly_connected(G):
                stats["connectivity"]["weakly_connected"] = True
                stats["connectivity"]["diameter"] = nx.diameter(G.to_undirected())
            else:
                stats["connectivity"]["weakly_connected"] = False
                stats["connectivity"]["num_components"] = nx.number_weakly_connected_components(G)

            # Centrality metrics (top 5 nodes)
            degree_centrality = nx.degree_centrality(G)
            betweenness_centrality = nx.betweenness_centrality(G)
            pagerank = nx.pagerank(G)

            stats["centrality"]["top_degree"] = sorted(
                degree_centrality.items(), key=lambda x: x[1], reverse=True
            )[:5]

            stats["centrality"]["top_betweenness"] = sorted(
                betweenness_centrality.items(), key=lambda x: x[1], reverse=True
            )[:5]

            stats["centrality"]["top_pagerank"] = sorted(
                pagerank.items(), key=lambda x: x[1], reverse=True
            )[:5]

            # Component analysis
            components = list(nx.weakly_connected_components(G))
            stats["components"]["count"] = len(components)
            stats["components"]["largest_size"] = len(max(components, key=len)) if components else 0

        except Exception as e:
            logger.warning(f"Failed to compute some graph statistics: {e}")

        return stats

    def export_to_gexf(self, G: nx.DiGraph, output_path: str) -> bool:
        """Export NetworkX graph to GEXF format for visualization tools."""
        try:
            nx.write_gexf(G, output_path)
            logger.info(f"Exported NetworkX graph to GEXF: {output_path}")
            return True
        except Exception as e:
            logger.error(f"GEXF export failed: {e}")
            return False

    def export_to_graphml(self, G: nx.DiGraph, output_path: str) -> bool:
        """Export NetworkX graph to GraphML format."""
        try:
            nx.write_graphml(G, output_path)
            logger.info(f"Exported NetworkX graph to GraphML: {output_path}")
            return True
        except Exception as e:
            logger.error(f"GraphML export failed: {e}")
            return False

    def find_shortest_path(
        self,
        G: nx.DiGraph,
        source_id: str,
        target_id: str
    ) -> Optional[list]:
        """Find shortest path between two nodes."""
        try:
            if source_id not in G or target_id not in G:
                logger.warning(f"Node not found: {source_id} or {target_id}")
                return None

            path = nx.shortest_path(G, source=source_id, target=target_id)
            return path
        except nx.NetworkXNoPath:
            logger.info(f"No path found between {source_id} and {target_id}")
            return None
        except Exception as e:
            logger.error(f"Shortest path computation failed: {e}")
            return None

    def get_neighbors(self, G: nx.DiGraph, node_id: str, depth: int = 1) -> Dict[str, Any]:
        """Get neighbors of a node up to a certain depth."""
        try:
            if node_id not in G:
                logger.warning(f"Node not found: {node_id}")
                return {"neighbors": [], "node_count": 0}

            neighbors = []
            visited = set()
            queue = [(node_id, 0)]

            while queue:
                current, current_depth = queue.pop(0)
                if current in visited or current_depth > depth:
                    continue

                visited.add(current)

                if current != node_id:
                    neighbors.append({
                        "node_id": current,
                        "depth": current_depth,
                        "attributes": dict(G.nodes[current]),
                    })

                if current_depth < depth:
                    for neighbor in G.successors(current):
                        queue.append((neighbor, current_depth + 1))
                    for neighbor in G.predecessors(current):
                        queue.append((neighbor, current_depth + 1))

            return {
                "node_id": node_id,
                "neighbors": neighbors,
                "node_count": len(neighbors),
            }

        except Exception as e:
            logger.error(f"Get neighbors failed for node {node_id}: {e}")
            return {"neighbors": [], "node_count": 0}