"""REST endpoint for Nexus Grid graph data — TASK-5-019.

Endpoints:
  GET /api/nexus/graph       — Returns code nodes + edges for Cytoscape.js rendering.
  GET /api/nexus/graph3d     — Returns 3D-optimised graph for Three.js (TASK-8-017).
  GET /api/nexus/bug-counts  — Bug-count aggregation per code_node (TASK-7-014).
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor
from app.services import nexus_service

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
    nodes, edges_list = await nexus_service.get_graph_data(db, project_id)

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


# ── Nexus Grid 3D endpoint (TASK-8-017) ───────────────────────────────────────


class Node3DItem(BaseModel):
    id: str
    label: str
    type: str
    x: float
    y: float
    z: float
    fog_of_war: bool
    discovery_count: int


class Edge3DItem(BaseModel):
    source: str
    target: str
    type: str


class NexusGraph3DResponse(BaseModel):
    nodes: list[Node3DItem]
    edges: list[Edge3DItem]
    total_nodes: int
    page: int
    page_size: int
    has_more: bool


@router.get("/graph3d", response_model=NexusGraph3DResponse)
async def get_nexus_graph3d(
    project_id: Optional[uuid.UUID] = Query(None, description="Filter by project UUID"),
    page: int = Query(0, ge=0, description="Zero-based page index"),
    page_size: int = Query(500, ge=1, le=2000, description="Nodes per page"),
    db: AsyncSession = Depends(get_db),
) -> NexusGraph3DResponse:
    """Return 3D-optimised graph payload for Three.js rendering (TASK-8-017).

    Positions are seeded from the node UUID so they are stable across requests.
    """
    total_nodes, nodes, edges_list = await nexus_service.get_graph3d_data(
        db, project_id, page, page_size
    )

    node_items: list[Node3DItem] = []
    for n in nodes:
        x, y, z = nexus_service.stable_coords(n.id, n.node_type)
        node_items.append(
            Node3DItem(
                id=str(n.id),
                label=n.label,
                type=n.node_type,
                x=x,
                y=y,
                z=z,
                fog_of_war=(n.explored_at is None),
                discovery_count=0,  # extended in future phase
            )
        )

    edge_items = [
        Edge3DItem(
            source=str(e.source_id),
            target=str(e.target_id),
            type=e.edge_type,
        )
        for e in edges_list
    ]

    return NexusGraph3DResponse(
        nodes=node_items,
        edges=edge_items,
        total_nodes=total_nodes,
        page=page,
        page_size=page_size,
        has_more=(page * page_size + len(nodes)) < total_nodes,
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

    rows = await nexus_service.get_bug_counts_data(db, project_id)

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
