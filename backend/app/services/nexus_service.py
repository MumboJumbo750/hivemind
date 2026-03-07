"""Service layer for Nexus Grid graph data.

Enthält alle DB-Zugriffe für nexus.py (graph, graph3d, bug-counts).
"""
import hashlib
import random
import uuid
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.code_node import CodeEdge, CodeNode
from app.models.node_bug_report import NodeBugReport

# Y-layer per node_type (used as stable "depth" hint for Three.js)
NODE_TYPE_Y: dict[str, float] = {
    "file": 0.0,
    "module": 10.0,
    "class": 20.0,
    "function": 30.0,
}


def stable_coords(node_id: uuid.UUID, node_type: str) -> tuple[float, float, float]:
    """Return deterministic (x, y, z) coordinates seeded from the node UUID."""
    seed_int = int(hashlib.md5(node_id.bytes, usedforsecurity=False).hexdigest(), 16)  # noqa: S324
    rng = random.Random(seed_int)  # noqa: S311
    x = round(rng.uniform(-50.0, 50.0), 3)
    y = NODE_TYPE_Y.get(node_type, 15.0)
    z = round(rng.uniform(-25.0, 25.0), 3)
    return x, y, z


async def get_graph_data(
    db: AsyncSession,
    project_id: Optional[uuid.UUID] = None,
) -> tuple[list[CodeNode], list[CodeEdge]]:
    """Fetch all nodes (optionally filtered by project) and their connected edges."""
    nodes_query = select(CodeNode)
    if project_id:
        nodes_query = nodes_query.where(CodeNode.project_id == project_id)

    result = await db.execute(nodes_query)
    nodes = list(result.scalars().all())
    node_ids = {n.id for n in nodes}

    edges: list[CodeEdge] = []
    if node_ids:
        edges_result = await db.execute(
            select(CodeEdge).where(
                or_(
                    CodeEdge.source_id.in_(node_ids),
                    CodeEdge.target_id.in_(node_ids),
                )
            )
        )
        edges = list(edges_result.scalars().all())

    return nodes, edges


async def get_graph3d_data(
    db: AsyncSession,
    project_id: Optional[uuid.UUID] = None,
    page: int = 0,
    page_size: int = 500,
) -> tuple[int, list[CodeNode], list[CodeEdge]]:
    """Fetch paginated nodes + connected edges for 3D rendering. Returns (total_nodes, nodes, edges)."""
    count_stmt = select(func.count()).select_from(CodeNode)
    if project_id:
        count_stmt = count_stmt.where(CodeNode.project_id == project_id)
    total_nodes: int = (await db.execute(count_stmt)).scalar_one()

    nodes_stmt = select(CodeNode).offset(page * page_size).limit(page_size)
    if project_id:
        nodes_stmt = nodes_stmt.where(CodeNode.project_id == project_id)
    nodes = list((await db.execute(nodes_stmt)).scalars().all())
    node_ids = {n.id for n in nodes}

    edges: list[CodeEdge] = []
    if node_ids:
        edges_result = await db.execute(
            select(CodeEdge).where(
                or_(
                    CodeEdge.source_id.in_(node_ids),
                    CodeEdge.target_id.in_(node_ids),
                )
            )
        )
        edges = list(edges_result.scalars().all())

    return total_nodes, nodes, edges


async def get_bug_counts_data(
    db: AsyncSession,
    project_id: Optional[uuid.UUID] = None,
) -> list:
    """Aggregate bug counts per code_node, optionally filtered by project."""
    if project_id:
        stmt = (
            select(
                NodeBugReport.node_id,
                func.sum(NodeBugReport.count).label("total_count"),
                func.json_agg(
                    func.json_build_object(
                        "sentry_issue_id", NodeBugReport.sentry_issue_id,
                        "count", NodeBugReport.count,
                        "last_seen", NodeBugReport.last_seen,
                        "stack_trace_hash", NodeBugReport.stack_trace_hash,
                    )
                ).label("issues"),
            )
            .join(CodeNode, CodeNode.id == NodeBugReport.node_id)
            .where(
                NodeBugReport.node_id.is_not(None),
                CodeNode.project_id == project_id,
            )
            .group_by(NodeBugReport.node_id)
        )
    else:
        stmt = (
            select(
                NodeBugReport.node_id,
                func.sum(NodeBugReport.count).label("total_count"),
                func.json_agg(
                    func.json_build_object(
                        "sentry_issue_id", NodeBugReport.sentry_issue_id,
                        "count", NodeBugReport.count,
                        "last_seen", NodeBugReport.last_seen,
                        "stack_trace_hash", NodeBugReport.stack_trace_hash,
                    )
                ).label("issues"),
            )
            .where(NodeBugReport.node_id.is_not(None))
            .group_by(NodeBugReport.node_id)
        )

    result = await db.execute(stmt)
    return result.all()
