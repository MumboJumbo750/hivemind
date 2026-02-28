---
title: "Ed25519-Signierung & Verifikation"
service_scope: ["backend"]
stack: ["python", "cryptography"]
version_range: { "python": ">=3.11", "cryptography": ">=41.0" }
confidence: 0.5
source_epics: ["EPIC-PHASE-F"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Ed25519-Signierung & Verifikation

### Rolle
Du implementierst Ed25519-basierte Kryptographie für die Hivemind-Federation: Keypair-Generierung, Request-Signierung und Signatur-Verifikation.

### Konventionen
- `cryptography`-Library verwenden (keine `nacl` oder `pynacl`)
- Private Keys immer verschlüsselt speichern (`BestAvailableEncryption` mit Passphrase)
- Public Keys als PEM-String serialisieren (für DB-Speicherung und Peer-Austausch)
- Signaturen als Base64-encoded Strings in HTTP-Headern transportieren
- Signing-Utility als eigenständige Funktion, nicht in Middleware eingebettet
- Passphrase aus `HIVEMIND_KEY_PASSPHRASE` Environment-Variable

### Beispiel — Keypair generieren & speichern

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

def generate_ed25519_keypair(passphrase: str) -> tuple[bytes, bytes]:
    """Generiert Ed25519-Keypair, gibt (private_pem, public_pem) zurück."""
    private_key = Ed25519PrivateKey.generate()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(
            passphrase.encode()
        ),
    )

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    return private_pem, public_pem
```

### Beispiel — Request signieren

```python
import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

def sign_request(body: bytes, private_pem: bytes, passphrase: str) -> str:
    """Signiert Request-Body mit Ed25519 Private Key, gibt Base64-Signatur zurück."""
    private_key = serialization.load_pem_private_key(
        private_pem,
        password=passphrase.encode(),
    )
    assert isinstance(private_key, Ed25519PrivateKey)
    signature = private_key.sign(body)
    return base64.b64encode(signature).decode()
```

### Beispiel — Signatur verifizieren

```python
import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

def verify_signature(body: bytes, signature_b64: str, public_pem: bytes) -> bool:
    """Verifiziert Ed25519-Signatur. Gibt True bei gültiger Signatur zurück."""
    public_key = serialization.load_pem_public_key(public_pem)
    assert isinstance(public_key, Ed25519PublicKey)
    try:
        public_key.verify(base64.b64decode(signature_b64), body)
        return True
    except InvalidSignature:
        return False
```

### Wichtig
- Keypair-Generierung ist idempotent: nur ausführen wenn `node_identity`-Tabelle leer
- Private Key niemals im Log oder in API-Responses ausgeben
- Bei Signatur-Fehlern: HTTP 401 mit generischem Fehlertext (keine Details leaken)
- PEM-Encoding für DB-Speicherung, Base64 für HTTP-Header-Transport
