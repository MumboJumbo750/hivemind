"""Federation Ed25519 Signature Middleware + signing utility — TASK-F-003.

Validates incoming ``/federation/*`` requests via Ed25519 signatures.
Also provides ``sign_request()`` for signing outgoing Federation requests.
"""
import base64
import logging
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)
from fastapi import Request, Response
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import settings
from app.db import AsyncSessionLocal
from app.models.federation import Node, NodeIdentity

logger = logging.getLogger(__name__)


class FederationSignatureMiddleware(BaseHTTPMiddleware):
    """Validate Ed25519 signatures on all ``/federation/*`` routes (except /federation/ping)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Only intercept federation routes (but not ping which is public)
        if not request.url.path.startswith("/federation/"):
            return await call_next(request)

        # GET /federation/ping is public — no signature needed
        if request.url.path == "/federation/ping" and request.method == "GET":
            return await call_next(request)

        # Skip if federation disabled
        if not settings.hivemind_federation_enabled:
            return Response(content='{"detail":"Federation disabled"}', status_code=503, media_type="application/json")

        # Extract required headers
        node_id_header = request.headers.get("X-Node-ID")
        signature_header = request.headers.get("X-Node-Signature")

        if not node_id_header or not signature_header:
            return Response(
                content='{"detail":"Missing X-Node-ID or X-Node-Signature header"}',
                status_code=401,
                media_type="application/json",
            )

        # Parse node_id
        try:
            node_id = uuid.UUID(node_id_header)
        except ValueError:
            return Response(
                content='{"detail":"Invalid X-Node-ID format"}',
                status_code=401,
                media_type="application/json",
            )

        # Read request body
        body = await request.body()

        # Verify signature against node's public key
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Node).where(Node.id == node_id))
            node = result.scalar_one_or_none()

            if node is None:
                return Response(
                    content='{"detail":"Unknown node"}',
                    status_code=401,
                    media_type="application/json",
                )

            if node.status != "active":
                return Response(
                    content='{"detail":"Node is not active"}',
                    status_code=401,
                    media_type="application/json",
                )

            if not node.public_key:
                return Response(
                    content='{"detail":"Node has no public key"}',
                    status_code=401,
                    media_type="application/json",
                )

            try:
                public_key = load_pem_public_key(node.public_key.encode())
                signature_bytes = base64.b64decode(signature_header)
                if not isinstance(public_key, Ed25519PublicKey):
                    raise ValueError("Not an Ed25519 key")
                public_key.verify(signature_bytes, body)
            except (InvalidSignature, ValueError, Exception) as exc:
                logger.warning("Invalid federation signature from node %s: %s", node_id, exc)
                return Response(
                    content='{"detail":"Invalid signature"}',
                    status_code=401,
                    media_type="application/json",
                )

        # Inject node_id into request state for downstream handlers
        request.state.federation_node_id = node_id

        return await call_next(request)


async def sign_request(body: bytes) -> tuple[str, str]:
    """Sign a request body with the local node's private key.

    Returns:
        Tuple of (node_id_str, base64_signature).
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(NodeIdentity))
        identity = result.scalar_one_or_none()
        if identity is None:
            raise RuntimeError("Node identity not bootstrapped — cannot sign federation requests.")

        passphrase = settings.hivemind_key_passphrase
        password = passphrase.encode() if passphrase else None
        private_key = load_pem_private_key(identity.private_key.encode(), password=password)

        signature = private_key.sign(body)
        return str(identity.node_id), base64.b64encode(signature).decode()
