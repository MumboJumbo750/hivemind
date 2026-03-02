"""REST endpoint for Nexus Grid graph data — TASK-5-019.

Endpoints:
  GET /api/nexus/graph       — Returns code nodes + edges for Cytoscape.js rendering.
  GET /api/nexus/bug-counts  — Bug-count aggregation per code_node (TASK-7-014).
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.code_node import CodeEdge, CodeNode
from app.models.node_bug_report import NodeBugReport
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor

router = APIRouter(prefix="/nexus", tags=["nexus"])


class NexusNodeResponse(BaseModel):
    id: str
    path: str
    node_type: str
    label: str
    project_id: Optional[str] = None
    explored_at: Optional[str] = None
    metadata: Optional[dict] = None

    model_config = {"from_attributes": True}


class NexusEdgeResponse(BaseModel):
    id: str
    source_id: str
    target_id: str
    edge_type: str

    model_config = {"from_attributes": True}


class NexusGraphResponse(BaseModel):
    nodes: list[NexusNodeResponse]
    edges: list[NexusEdgeResponse]
    total_nodes: int
    explored_count: int
    unexplored_count: int


@router.get("/graph", response_model=NexusGraphResponse)
async def get_nexus_graph(
    project_id: Optional[uuid.UUID] = Query(None, description="Filter by project"),
    db: AsyncSession = Depends(get_db),
):
    """Return code nodes + edges for Nexus Grid visualization."""
    nodes_query = select(CodeNode)
    if project_id:
        nodes_query = nodes_query.where(CodeNode.project_id == project_id)

    result = await db.execute(nodes_query)
    nodes = result.scalars().all()
    node_ids = {n.id for n in nodes}

    # Fetch edges connected to these nodes
    edges_list: list[CodeEdge] = []
    if node_ids:
        edges_result = await db.execute(
            select(CodeEdge).where(
                or_(
                    CodeEdge.source_id.in_(node_ids),
                    CodeEdge.target_id.in_(node_ids),
                )
            )
        )
        edges_list = list(edges_result.scalars().all())

    explored = sum(1 for n in nodes if n.explored_at is not None)

    return NexusGraphResponse(
        nodes=[
            NexusNodeResponse(
                id=str(n.id),
                path=n.path,
                node_type=n.node_type,
                label=n.label,
                project_id=str(n.project_id) if n.project_id else None,
                explored_at=n.explored_at.isoformat() if n.explored_at else None,
                metadata=n.metadata_,
            )
            for n in nodes
        ],
        edges=[
            NexusEdgeResponse(
                id=str(e.id),
                source_id=str(e.source_id),
                target_id=str(e.target_id),
                edge_type=e.edge_type,
            )
            for e in edges_list
        ],
        total_nodes=len(nodes),
        explored_count=explored,
        unexplored_count=len(nodes) - explored,
    )


# ── Bug-Heatmap data (TASK-7-014) ─────────────────────────────────────────────


class BugIssueDetail(BaseModel):
    sentry_issue_id: Optional[str] = None
    count: int
    last_seen: Optional[str] = None
    stack_trace_hash: Optional[str] = None


class NodeBugCountItem(BaseModel):
    node_id: str
    bug_count: int
    sentry_issues: list[BugIssueDetail]


@router.get("/bug-counts", response_model=list[NodeBugCountItem])
async def get_bug_counts(
    project_id: Optional[uuid.UUID] = Query(None, description="Filter by project"),
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> list[NodeBugCountItem]:
    """Return aggregated bug counts per code_node for the Bug-Heatmap layer."""
    del actor

    # Aggregate bug reports grouped by node_id
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

    if project_id:
        # Join code_nodes to filter by project
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

    result = await db.execute(stmt)
    rows = result.all()

    items: list[NodeBugCountItem] = []
    for row in rows:
        issues_raw = row.issues or []
        issues = [
            BugIssueDetail(
                sentry_issue_id=issue.get("sentry_issue_id"),
                count=int(issue.get("count") or 1),
                last_seen=issue.get("last_seen"),
                stack_trace_hash=issue.get("stack_trace_hash"),
            )
            for issue in issues_raw
            if isinstance(issue, dict)
        ]
        items.append(
            NodeBugCountItem(
                node_id=str(row.node_id),
                bug_count=int(row.total_count or 0),
                sentry_issues=issues,
            )
        )

    return items
