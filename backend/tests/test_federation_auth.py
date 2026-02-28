"""Unit-Tests für die Ed25519-Signatur-Middleware (TASK-F-003)."""
import base64
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


def _make_keypair():
    """Generate an Ed25519 keypair for tests."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    private_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    return private_key, public_pem, private_pem


def _sign(private_key, body: bytes) -> str:
    """Sign body and return base64 signature."""
    sig = private_key.sign(body)
    return base64.b64encode(sig).decode()


@pytest.mark.asyncio
async def test_sign_request_returns_node_id_and_signature():
    """sign_request() signs body with local private key."""
    private_key, public_pem, private_pem = _make_keypair()
    node_id = uuid.uuid4()

    identity_mock = MagicMock()
    identity_mock.node_id = node_id
    identity_mock.private_key = private_pem

    db_mock = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = identity_mock
    db_mock.execute.return_value = result_mock

    # Patch AsyncSessionLocal context manager
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=db_mock)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.federation_auth.AsyncSessionLocal", return_value=session_cm), \
         patch("app.services.federation_auth.settings") as mock_settings:
        mock_settings.hivemind_key_passphrase = ""

        from app.services.federation_auth import sign_request
        returned_node_id, signature = await sign_request(b'test body')

    assert returned_node_id == str(node_id)
    # Verify signature is valid base64
    sig_bytes = base64.b64decode(signature)
    assert len(sig_bytes) == 64  # Ed25519 signatures are always 64 bytes


@pytest.mark.asyncio
async def test_middleware_passes_non_federation_routes():
    """Non-federation routes are not affected by middleware."""
    from app.services.federation_auth import FederationSignatureMiddleware

    request = MagicMock()
    request.url.path = "/api/tasks"
    
    call_next = AsyncMock(return_value=MagicMock(status_code=200))
    
    middleware = FederationSignatureMiddleware(app=MagicMock())
    result = await middleware.dispatch(request, call_next)
    
    call_next.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_middleware_allows_ping_without_signature():
    """GET /federation/ping is public."""
    from app.services.federation_auth import FederationSignatureMiddleware

    request = MagicMock()
    request.url.path = "/federation/ping"
    request.method = "GET"
    
    call_next = AsyncMock(return_value=MagicMock(status_code=200))
    
    middleware = FederationSignatureMiddleware(app=MagicMock())
    result = await middleware.dispatch(request, call_next)
    
    call_next.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_middleware_rejects_missing_headers():
    """Missing X-Node-ID or X-Node-Signature → 401."""
    from app.services.federation_auth import FederationSignatureMiddleware

    request = MagicMock()
    request.url.path = "/federation/skill/publish"
    request.method = "POST"
    request.headers = {}
    
    call_next = AsyncMock()
    
    with patch("app.services.federation_auth.settings") as s:
        s.hivemind_federation_enabled = True
        middleware = FederationSignatureMiddleware(app=MagicMock())
        result = await middleware.dispatch(request, call_next)
    
    assert result.status_code == 401
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_middleware_rejects_invalid_signature():
    """Invalid signature → 401."""
    from app.services.federation_auth import FederationSignatureMiddleware

    node_id = uuid.uuid4()
    _, public_pem, _ = _make_keypair()

    # Node with this public key
    node_mock = MagicMock()
    node_mock.status = "active"
    node_mock.public_key = public_pem

    db_mock = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = node_mock
    db_mock.execute.return_value = result_mock

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=db_mock)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    request = MagicMock()
    request.url.path = "/federation/skill/publish"
    request.method = "POST"
    request.headers = {
        "X-Node-ID": str(node_id),
        "X-Node-Signature": base64.b64encode(b"badsignature" * 6).decode(),
    }
    request.body = AsyncMock(return_value=b'{"test": true}')

    call_next = AsyncMock()

    with patch("app.services.federation_auth.AsyncSessionLocal", return_value=session_cm), \
         patch("app.services.federation_auth.settings") as s:
        s.hivemind_federation_enabled = True
        middleware = FederationSignatureMiddleware(app=MagicMock())
        result = await middleware.dispatch(request, call_next)

    assert result.status_code == 401
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_middleware_accepts_valid_signature():
    """Valid Ed25519 signature → passes to handler."""
    from app.services.federation_auth import FederationSignatureMiddleware

    private_key, public_pem, _ = _make_keypair()
    node_id = uuid.uuid4()
    body = b'{"skill":"test"}'
    signature = _sign(private_key, body)

    node_mock = MagicMock()
    node_mock.status = "active"
    node_mock.public_key = public_pem

    db_mock = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = node_mock
    db_mock.execute.return_value = result_mock

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=db_mock)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    request = MagicMock()
    request.url.path = "/federation/skill/publish"
    request.method = "POST"
    request.headers = {
        "X-Node-ID": str(node_id),
        "X-Node-Signature": signature,
    }
    request.body = AsyncMock(return_value=body)
    request.state = MagicMock()

    call_next = AsyncMock(return_value=MagicMock(status_code=200))

    with patch("app.services.federation_auth.AsyncSessionLocal", return_value=session_cm), \
         patch("app.services.federation_auth.settings") as s:
        s.hivemind_federation_enabled = True
        middleware = FederationSignatureMiddleware(app=MagicMock())
        result = await middleware.dispatch(request, call_next)

    call_next.assert_awaited_once()
    assert request.state.federation_node_id == node_id


@pytest.mark.asyncio
async def test_middleware_rejects_inactive_node():
    """Blocked/inactive peer → 401."""
    from app.services.federation_auth import FederationSignatureMiddleware

    private_key, public_pem, _ = _make_keypair()
    node_id = uuid.uuid4()
    body = b'{"test": true}'
    signature = _sign(private_key, body)

    node_mock = MagicMock()
    node_mock.status = "blocked"
    node_mock.public_key = public_pem

    db_mock = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = node_mock
    db_mock.execute.return_value = result_mock

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=db_mock)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    request = MagicMock()
    request.url.path = "/federation/skill/publish"
    request.method = "POST"
    request.headers = {
        "X-Node-ID": str(node_id),
        "X-Node-Signature": signature,
    }
    request.body = AsyncMock(return_value=body)

    call_next = AsyncMock()

    with patch("app.services.federation_auth.AsyncSessionLocal", return_value=session_cm), \
         patch("app.services.federation_auth.settings") as s:
        s.hivemind_federation_enabled = True
        middleware = FederationSignatureMiddleware(app=MagicMock())
        result = await middleware.dispatch(request, call_next)

    assert result.status_code == 401
    call_next.assert_not_awaited()
