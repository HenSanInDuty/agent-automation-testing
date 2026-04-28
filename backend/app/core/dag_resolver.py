"""
core/dag_resolver.py – DAG validation and execution-order resolver.

Validates pipeline template DAGs (checks for cycles, missing INPUT/OUTPUT
nodes, orphan nodes, dangling edge references) and computes the parallel
execution layers for the DAGPipelineRunner.

Usage::

    from app.core.dag_resolver import DAGResolver, DAGValidationError
    from app.db.models import PipelineNodeConfig, PipelineEdgeConfig

    resolver = DAGResolver(nodes, edges)
    topo_order = resolver.validate()       # raises DAGValidationError if invalid
    layers = resolver.get_execution_layers()  # [[input], [agent_a, agent_b], ...]
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.db.models import PipelineEdgeConfig, PipelineNodeConfig


class DAGValidationError(Exception):
    """Raised when pipeline DAG is invalid."""


class DAGResolver:
    """
    Validates and resolves execution order for a pipeline DAG.

    Uses Kahn's algorithm for topological sort (cycle detection) and
    longest-path layering for parallel execution grouping.

    Attributes:
        nodes:      Dict of node_id → PipelineNodeConfig.
        edges:      List of PipelineEdgeConfig.
    """

    def __init__(
        self,
        nodes: "list[PipelineNodeConfig]",
        edges: "list[PipelineEdgeConfig]",
    ) -> None:
        self.nodes: dict[str, "PipelineNodeConfig"] = {n.node_id: n for n in nodes}
        self.edges: list["PipelineEdgeConfig"] = edges

        # Adjacency list: source → [targets]
        self._adj: dict[str, list[str]] = {n.node_id: [] for n in nodes}
        # In-degree count for Kahn's algorithm
        self._in_degree: dict[str, int] = {n.node_id: 0 for n in nodes}

        for edge in edges:
            if edge.source_node_id in self._adj:
                self._adj[edge.source_node_id].append(edge.target_node_id)
            if edge.target_node_id in self._in_degree:
                self._in_degree[edge.target_node_id] += 1

    def validate(self) -> list[str]:
        """
        Validate the DAG and return topological order.

        Checks performed:
        1. Exactly 1 INPUT node exists.
        2. Exactly 1 OUTPUT node exists.
        3. All edge source/target references resolve to existing nodes.
        4. No cycles (Kahn's algorithm).
        5. All enabled nodes are reachable from the INPUT node (orphan check).

        Returns:
            Topological order as list of node_ids.

        Raises:
            DAGValidationError: If any check fails. The error message
                contains all failures joined by "; ".
        """
        # Import here to avoid circular import at module level
        from app.db.models import NodeType

        errors: list[str] = []

        # 1. Check INPUT node (exactly 1)
        input_nodes = [n for n in self.nodes.values() if n.node_type == NodeType.INPUT]
        if len(input_nodes) != 1:
            errors.append(
                f"Pipeline must have exactly 1 INPUT node, found {len(input_nodes)}"
            )

        # 2. Check OUTPUT node (exactly 1)
        output_nodes = [
            n for n in self.nodes.values() if n.node_type == NodeType.OUTPUT
        ]
        if len(output_nodes) != 1:
            errors.append(
                f"Pipeline must have exactly 1 OUTPUT node, found {len(output_nodes)}"
            )

        # 3. Check all edge references exist
        for edge in self.edges:
            if edge.source_node_id not in self.nodes:
                errors.append(
                    f"Edge '{edge.edge_id}': source '{edge.source_node_id}' not found in nodes"
                )
            if edge.target_node_id not in self.nodes:
                errors.append(
                    f"Edge '{edge.edge_id}': target '{edge.target_node_id}' not found in nodes"
                )

        # 4. Check for cycles using Kahn's algorithm
        # Only run if there are no dangling edge refs — otherwise _topological_sort
        # would KeyError on unknown node IDs in the in-degree map.
        has_dangling = any(
            e.source_node_id not in self.nodes or e.target_node_id not in self.nodes
            for e in self.edges
        )
        if has_dangling:
            topo_order = None
        else:
            topo_order = self._topological_sort()
            if topo_order is None:
                errors.append("Pipeline contains a cycle — DAG must be acyclic")

        # 5. Connectivity check (all enabled nodes reachable from INPUT)
        if input_nodes and topo_order is not None:
            reachable = self._bfs(input_nodes[0].node_id)
            unreachable = set(self.nodes.keys()) - reachable
            enabled_unreachable = [
                nid for nid in unreachable if self.nodes[nid].enabled
            ]
            if enabled_unreachable:
                errors.append(
                    f"Orphan nodes not reachable from INPUT: {enabled_unreachable}"
                )

        if errors:
            raise DAGValidationError("; ".join(errors))

        return topo_order  # type: ignore[return-value]

    def get_execution_layers(self) -> list[list[str]]:
        """
        Group enabled nodes into parallel execution layers.

        Nodes in the same layer have no dependency on each other and can
        run concurrently.  Computed using longest-path layering after
        a successful topological sort.

        Returns:
            List of layers.  Each layer is a list of node_ids.
            Example::

                [["__input__"], ["agent_a", "agent_b"], ["agent_c"], ["__output__"]]

        Raises:
            DAGValidationError: If the DAG is invalid (propagates from
                :meth:`validate`).
        """
        topo_order = self.validate()

        # Compute depth (= longest path from any root) for each node
        depth: dict[str, int] = {}
        for node_id in topo_order:
            parents = [
                e.source_node_id for e in self.edges if e.target_node_id == node_id
            ]
            if not parents:
                depth[node_id] = 0
            else:
                depth[node_id] = max(depth.get(p, 0) for p in parents) + 1

        # Group by depth, skip disabled nodes
        max_depth = max(depth.values()) if depth else 0
        layers: list[list[str]] = [[] for _ in range(max_depth + 1)]
        for node_id, d in depth.items():
            if self.nodes[node_id].enabled:
                layers[d].append(node_id)

        # Filter out empty layers (can occur if all nodes at a depth are disabled)
        return [layer for layer in layers if layer]

    def get_node_parents(self, node_id: str) -> list[str]:
        """Return direct parent node_ids (nodes that have an edge into *node_id*)."""
        return [e.source_node_id for e in self.edges if e.target_node_id == node_id]

    def get_node_children(self, node_id: str) -> list[str]:
        """Return direct child node_ids (nodes that *node_id* has an edge into)."""
        return list(self._adj.get(node_id, []))

    def _topological_sort(self) -> Optional[list[str]]:
        """
        Kahn's algorithm for topological sort.

        Returns:
            Topological order as a list of node_ids, or ``None`` if a cycle
            is detected (i.e. the resulting order is shorter than the node count).
        """
        in_degree = dict(self._in_degree)
        queue: deque[str] = deque(
            node_id for node_id, deg in in_degree.items() if deg == 0
        )
        order: list[str] = []

        while queue:
            node_id = queue.popleft()
            order.append(node_id)
            for child in self._adj.get(node_id, []):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(order) != len(self.nodes):
            return None  # Cycle detected

        return order

    def _bfs(self, start: str) -> set[str]:
        """
        BFS from *start*, returning all reachable node_ids (including *start*).
        """
        visited: set[str] = {start}
        queue: deque[str] = deque([start])
        while queue:
            node_id = queue.popleft()
            for child in self._adj.get(node_id, []):
                if child not in visited:
                    visited.add(child)
                    queue.append(child)
        return visited


def merge_inputs(parent_outputs: dict[str, dict]) -> dict:  # type: ignore[type-arg]
    """
    Merge outputs from multiple parent nodes into a single input dict.

    Each parent's output is namespaced under its node_id to avoid key
    collisions.  A convenience ``__flat__`` key contains a shallow merge
    of all parent outputs (last write wins on collision).

    Args:
        parent_outputs: Mapping of ``{ parent_node_id: output_dict }``.

    Returns:
        Merged input dict for the current node.

    Example::

        merge_inputs({
            "agent_a": {"test_cases": [...]},
            "agent_b": {"coverage": 0.85},
        })
        # → {
        #     "agent_a": {"test_cases": [...]},
        #     "agent_b": {"coverage": 0.85},
        #     "__flat__": {"test_cases": [...], "coverage": 0.85},
        # }
    """
    merged: dict = {}  # type: ignore[type-arg]
    for parent_id, output in parent_outputs.items():
        merged[parent_id] = output

    flat: dict = {}  # type: ignore[type-arg]
    for output in parent_outputs.values():
        if isinstance(output, dict):
            flat.update(output)
    merged["__flat__"] = flat

    return merged
