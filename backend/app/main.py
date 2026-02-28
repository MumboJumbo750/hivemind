from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import AsyncSessionLocal
from app.routers import auth, code_nodes, events, guards, health, members, nodes, projects, epics, federation, search, settings as settings_router, skills, sync_outbox, tasks, webhooks, wiki
from app.mcp.transport import router as mcp_router
from app.services.federation_auth import FederationSignatureMiddleware
from app.services.node_bootstrap import bootstrap_node
from app.services.peers_loader import load_peers
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with AsyncSessionLocal() as db:
        await bootstrap_node(db)
        await load_peers(db)
        # Hub-assisted / hub-relay: register with Hive Station
        if settings.hivemind_federation_topology in ("hub_assisted", "hub_relay"):
            from app.services.hive_station import hive_station
            await hive_station.register(db)
            await hive_station.fetch_peers(db)
        await db.commit()
    start_scheduler()
    yield
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
    app.include_router(search.router, prefix="/api")
    app.include_router(skills.router, prefix="/api")
    app.include_router(nodes.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(wiki.router, prefix="/api")
    app.include_router(guards.router, prefix="/api")
    app.include_router(code_nodes.router, prefix="/api")
    app.include_router(webhooks.router, prefix="/api")
    app.include_router(sync_outbox.router, prefix="/api")
    app.include_router(federation.router)
    app.include_router(mcp_router, prefix="/api")

    return app


app = create_app()
