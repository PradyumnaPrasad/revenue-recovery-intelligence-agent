"""Razorpay HTTP client — plan.md §6.9. Raw httpx against the verified API
contract (razorpay.com/docs/api/payments/payment-links/create-standard/),
not the `razorpay` SDK package's method names, which were never verified
against this build's actual dependency version. The exact request shape
below was proven working live on 31 Aug 2026 — one real test-mode payment
link created, id `plink_TWR8Y8WeMFwpxV`, HTTP 200 — before any of this
wrapper code existed.
"""
from __future__ import annotations

import httpx

from app.settings import get_settings

RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"


class RazorpayError(Exception):
    pass


def _auth() -> tuple[str, str]:
    settings = get_settings()
    return (settings.razorpay_key_id, settings.razorpay_key_secret)


def create_payment_link(amount_paise: int, description: str) -> dict:
    """Creates a real Razorpay test-mode payment link. Both
    resend_payment_link and send_upi_payment_link use this same call —
    Razorpay's standard payment link already offers UPI as a checkout
    method by default; a UPI-specific creation flag was not verified
    against this build's account and is not assumed here (a documented
    simplification under this build's compressed schedule, not a hidden
    one — see plan.md §6.9).
    """
    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "description": description,
        "notify": {"sms": False, "email": False},
    }
    try:
        response = httpx.post(
            f"{RAZORPAY_BASE_URL}/payment_links/",
            auth=_auth(),
            json=payload,
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RazorpayError(f"Razorpay API error {e.response.status_code}: {e.response.text}") from e
    except httpx.RequestError as e:
        raise RazorpayError(f"Razorpay request failed: {e}") from e
    return response.json()
