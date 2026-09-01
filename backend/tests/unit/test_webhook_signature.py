"""plan.md §6.9 'Done when': tampered body -> 400, nothing written. Tests
the signature-verification logic in isolation — no DB, no live server.
"""
from __future__ import annotations

import hashlib
import hmac

from app.api.webhooks import _verify_signature

SECRET = "test_webhook_secret"


def _sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_passes():
    body = b'{"event": "payment_link.paid", "payload": {}}'
    signature = _sign(body)
    assert _verify_signature(body, signature, SECRET) is True


def test_tampered_body_fails_verification():
    body = b'{"event": "payment_link.paid", "payload": {}}'
    signature = _sign(body)
    tampered_body = b'{"event": "payment_link.paid", "payload": {"amount": 999999999}}'
    assert _verify_signature(tampered_body, signature, SECRET) is False


def test_wrong_secret_fails_verification():
    body = b'{"event": "payment.captured"}'
    signature = _sign(body, secret="a_different_secret")
    assert _verify_signature(body, signature, SECRET) is False


def test_empty_signature_fails():
    body = b'{"event": "payment.captured"}'
    assert _verify_signature(body, "", SECRET) is False


def test_empty_secret_fails():
    body = b'{"event": "payment.captured"}'
    signature = _sign(body)
    assert _verify_signature(body, signature, "") is False
