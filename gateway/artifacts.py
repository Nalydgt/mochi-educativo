"""ECDSA P-256 manifests. Sign exact payload bytes so embedded clients need no JSON canonicalizer."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


class ArtifactSigner:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            key = ec.generate_private_key(ec.SECP256R1())
            data = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption())
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, 'wb') as output:
                    output.write(data)
        self.key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(self.key, ec.EllipticCurvePrivateKey) or not isinstance(self.key.curve, ec.SECP256R1):
            raise ValueError('An ECDSA P-256 artifact key is required')

    def public_key(self):
        return self.key.public_key().public_bytes(serialization.Encoding.DER,
                                                 serialization.PublicFormat.SubjectPublicKeyInfo)

    def sign(self, payload: dict):
        data = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                          allow_nan=False).encode('ascii')
        signature = self.key.sign(data, ec.ECDSA(hashes.SHA256()))
        return {'payload': base64.b64encode(data).decode(), 'signature': base64.b64encode(signature).decode(),
                'algorithm': 'ecdsa-p256-sha256'}


def checked_id(value):
    if not re.fullmatch(r'[a-f0-9]{32}', value):
        raise ValueError('Invalid artifact identifier')
    return value


def verify_manifest(envelope: dict, public_der: bytes):
    if envelope.get('algorithm') != 'ecdsa-p256-sha256':
        raise ValueError('Unsupported signature')
    data = base64.b64decode(envelope['payload'], validate=True)
    if len(data) > 8192:
        raise ValueError('Manifest too large')
    key = serialization.load_der_public_key(public_der)
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError('Unexpected public key')
    key.verify(base64.b64decode(envelope['signature'], validate=True), data, ec.ECDSA(hashes.SHA256()))
    return json.loads(data)


def file_manifest(path: Path, *, kind: str, version: str, **metadata):
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    return {'schema': 1, 'kind': kind, 'version': version, 'size': path.stat().st_size,
            'sha256': digest, 'target': 'esp32s3', 'idf': '6.0.1', **metadata}
