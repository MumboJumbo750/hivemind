from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        ],
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        environment=settings.sentry_environment,
    )
from app.db import AsyncSessionLocal
from app.mcp.transport import mcp_standard_routes
from app.mcp.transport import router as mcp_router
from app.routers import (
    achievements,
    admin,
    agent_sessions,
    audit,
    governance_audit,
    auth,
    code_nodes,
    conductor,
    dispatch_policies,
    epic_proposals,
    epics,
    events,
    federation,
    guards,
    health,
    kpis,
    learning,
    memory,
    mcp_bridges,
    members,
    nexus,
    nodes,
    notifications,
    projects,
    search,
    skills,
    sync_outbox,
    tasks,
    triage,
    webhooks,
    wiki,
)
from app.routers import settings as settings_router
from app.services.federation_auth import FederationSignatureMiddleware
from app.services.embedding_service import get_embedding_service
from app.services.node_bootstrap import bootstrap_node
from app.services.peers_loader import load_peers
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if not settings.testing:
        async with AsyncSessionLocal() as db:
            await bootstrap_node(db)
            await load_peers(db)
            # Hub-assisted / hub-relay: register with Hive Station
            if settings.hivemind_federation_topology in ("hub_assisted", "hub_relay"):
                from app.services.hive_station import hive_station
                await hive_station.register(db)
                await hive_station.fetch_peers(db)
            await db.commit()
        await get_embedding_service().start_worker()
        start_scheduler()
    yield
    if not settings.testing:
        await get_embedding_service().stop_worker()
        stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Hivemind API",
        description="Hivemind — ein hybrides Entwickler-Hivemind mit Progressive Disclosure.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Federation signature validation (only active when federation enabled)
    if settings.hivemind_federation_enabled:
        app.add_middleware(FederationSignatureMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(projects.router, prefix="/api")
    app.include_router(epics.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(members.router, prefix="/api")
    app.include_router(settings_router.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(skills.router, prefix="/api")
    app.include_router(nodes.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(wiki.router, prefix="/api")
    app.include_router(guards.router, prefix="/api")
    app.include_router(code_nodes.router, prefix="/api")
    app.include_router(nexus.router, prefix="/api")
    app.include_router(webhooks.router, prefix="/api")
    app.include_router(sync_outbox.router, prefix="/api")
    app.include_router(epic_proposals.router, prefix="/api")
    app.include_router(audit.router, prefix="/api")
    app.include_router(achievements.router, prefix="/api")
    app.include_router(notifications.router, prefix="/api")
    app.include_router(triage.router, prefix="/api")
    app.include_router(kpis.router, prefix="/api")
    app.include_router(learning.router, prefix="/api")
    app.include_router(memory.router, prefix="/api")
    app.include_router(mcp_bridges.router, prefix="/api")
    app.include_router(conductor.router, prefix="/api")
    app.include_router(conductor.ide_router, prefix="/api")
    app.include_router(dispatch_policies.router, prefix="/api")
    app.include_router(agent_sessions.router, prefix="/api")
    app.include_router(governance_audit.router, prefix="/api")
    app.include_router(federation.router)
    app.include_router(mcp_router, prefix="/api")

    # Mount standard MCP SSE/message endpoints as raw Starlette routes
    # (they need ASGI scope/receive/send for the SDK transport)
    for route in mcp_standard_routes:
        app.routes.append(route)

    return app


app = create_app()
