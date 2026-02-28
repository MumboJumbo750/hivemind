"""Node-Bootstrap — Phase 2.

Beim ersten FastAPI-Start: Ed25519-Keypair generieren, eigenen Node in `nodes` anlegen
und Keypair in `node_identity` speichern. Idempotent: kein zweiter Node bei Neustart.
"""
import logging
import socket

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.federation import Node, NodeIdentity

logger = logging.getLogger(__name__)


async def bootstrap_node(db: AsyncSession) -> None:
    """Idempotent: nur ausführen wenn noch keine NodeIdentity existiert."""
    result = await db.execute(select(NodeIdentity))
    if result.scalar_one_or_none() is not None:
        logger.debug("Node already bootstrapped — skipping.")
        return

    node_name = settings.hivemind_node_name or socket.gethostname()
    node_url = settings.hivemind_node_url

    # Ed25519-Keypair generieren
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Private key encryption: use passphrase if configured, otherwise no encryption
    passphrase = settings.hivemind_key_passphrase
    encryption = (
        BestAvailableEncryption(passphrase.encode())
        if passphrase
        else NoEncryption()
    )

    private_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, encryption
    ).decode()
    public_pem = public_key.public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    ).decode()

    # Node anlegen
    node = Node(
        node_name=node_name,
        node_url=node_url,
        public_key=public_pem,
    )
    db.add(node)
    await db.flush()  # node.id befüllen

    # NodeIdentity anlegen
    identity = NodeIdentity(
        node_id=node.id,
        node_name=node_name,
        private_key=private_pem,
        public_key=public_pem,
    )
    db.add(identity)
    await db.flush()

    logger.info("Node bootstrapped: %s (%s)", node_name, node_url)
