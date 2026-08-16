from __future__ import annotations

import hashlib
import logging

from fastapi import HTTPException, status
from razorpay.errors import SignatureVerificationError

from src.app.core.config import settings
from src.app.core.razorpay_client import razorpay_client

logger = logging.getLogger(__name__)


def verify_signature(raw_body: bytes, signature: str | None) -> None:

    if not signature:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Missing X-Razorpay-Signature header."
        )

    try:
        razorpay_client.utility.verify_webhook_signature(
            raw_body.decode("utf-8"), signature, settings.razorpay_webhook_secret
        )
    except SignatureVerificationError as exc:
        logger.warning("Razorpay webhook signature verification failed.")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Invalid webhook signature."
        ) from exc


def compute_event_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()
