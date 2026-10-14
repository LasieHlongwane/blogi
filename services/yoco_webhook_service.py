
"""
KALXA CREATOR
YOCO WEBHOOK SIGNATURE VERIFICATION SERVICE

Purpose:
    Authenticate incoming Yoco webhook requests using
    the official Svix Python library.

Used by:
    routes/payments.py

Security:
    - Verify the original raw request body.
    - Require all three Svix signature headers.
    - Validate webhook timestamp freshness.
    - Verify the Svix cryptographic signature.
    - Never log secrets, signatures or payment bodies.
    - Never treat browser redirects as payment proof.

Environment:
    YOCO_WEBHOOK_SECRET=whsec_...

Important:
    YOCO_WEBHOOK_SECRET is different from:
        YOCO_SECRET_KEY
        YOCO_API_KEY

This module authenticates webhook deliveries only.
It does not activate plans, verify checkout amounts,
or calculate commissions.
"""

import time

from flask import current_app

from svix.webhooks import (
    Webhook,
    WebhookVerificationError,
)


# ============================================================
# EXCEPTION
# ============================================================

class YocoWebhookError(Exception):
    """
    Raised when a Yoco webhook cannot be authenticated.
    """

    pass


# ============================================================
# WEBHOOK SECRET
# ============================================================

def get_yoco_webhook_secret():
    """
    Retrieve the Yoco/Svix webhook signing secret.

    The secret must come from the webhook subscription
    configuration, not the Yoco payment API key.
    """

    secret = current_app.config.get(
        "YOCO_WEBHOOK_SECRET"
    )

    if not isinstance(secret, str):
        raise YocoWebhookError(
            "Yoco webhook secret is not configured."
        )

    secret = secret.strip()

    if not secret:
        raise YocoWebhookError(
            "Yoco webhook secret is empty."
        )

    if not secret.startswith("whsec_"):
        raise YocoWebhookError(
            "Yoco webhook secret has an invalid format."
        )

    return secret


# ============================================================
# RAW BODY VALIDATION
# ============================================================

def _normalize_raw_body(raw_body):
    """
    Accept the original webhook request body as bytes.

    Do not parse and re-serialize JSON before verifying
    the signature.

    The payment route should use:

        request.get_data(
            cache=True,
            as_text=False,
        )
    """

    if isinstance(raw_body, bytes):
        return raw_body

    if isinstance(raw_body, bytearray):
        return bytes(raw_body)

    raise YocoWebhookError(
        "Webhook body must be raw bytes."
    )


# ============================================================
# HEADER VALIDATION
# ============================================================

def _validate_headers(
    *,
    webhook_id,
    webhook_timestamp,
    webhook_signature,
):
    """
    Ensure required Svix headers are present and valid.
    """

    headers = {
        "webhook-id": webhook_id,
        "webhook-timestamp": webhook_timestamp,
        "webhook-signature": webhook_signature,
    }

    for name, value in headers.items():

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise YocoWebhookError(
                f"Missing or invalid {name} header."
            )

    return {
        name: value.strip()
        for name, value in headers.items()
    }


# ============================================================
# TIMESTAMP VALIDATION
# ============================================================

def _validate_timestamp(
    webhook_timestamp,
    tolerance_seconds,
):
    """
    Reject webhook deliveries with stale or future
    timestamps outside the allowed tolerance.

    This complements the Svix verifier's built-in
    timestamp checks.

    The timestamp must be Unix time in seconds.
    """

    if (
        isinstance(tolerance_seconds, bool)
        or not isinstance(tolerance_seconds, int)
        or tolerance_seconds <= 0
    ):
        raise YocoWebhookError(
            "Invalid webhook timestamp tolerance."
        )

    try:

        timestamp = int(
            webhook_timestamp
        )

    except (TypeError, ValueError) as exc:

        raise YocoWebhookError(
            "Invalid webhook timestamp."
        ) from exc

    if timestamp <= 0:
        raise YocoWebhookError(
            "Invalid webhook timestamp."
        )

    now = int(time.time())

    age_seconds = abs(
        now - timestamp
    )

    if age_seconds > tolerance_seconds:
        raise YocoWebhookError(
            "Webhook timestamp is outside "
            "the permitted time window."
        )

    return timestamp


# ============================================================
# VERIFY YOCO WEBHOOK
# ============================================================

def verify_yoco_webhook(
    *,
    raw_body,
    webhook_id,
    webhook_timestamp,
    webhook_signature,
    tolerance_seconds=300,
):
    """
    Verify an incoming Yoco webhook using Svix.

    Arguments:
        raw_body:
            Original HTTP request body as bytes.

        webhook_id:
            Value of the webhook-id header.

        webhook_timestamp:
            Value of the webhook-timestamp header.

        webhook_signature:
            Value of the webhook-signature header.

        tolerance_seconds:
            Maximum permitted clock difference.
            Default: 300 seconds (5 minutes).

    Returns:
        True when verification succeeds.

    Raises:
        YocoWebhookError on verification failure.

    This function is compatible with the existing
    routes/payments.py webhook handler.
    """

    # --------------------------------------------------------
    # 1. VALIDATE RAW BODY
    # --------------------------------------------------------

    body = _normalize_raw_body(
        raw_body
    )

    # --------------------------------------------------------
    # 2. VALIDATE HEADERS
    # --------------------------------------------------------

    headers = _validate_headers(
        webhook_id=webhook_id,
        webhook_timestamp=webhook_timestamp,
        webhook_signature=webhook_signature,
    )

    # --------------------------------------------------------
    # 3. VALIDATE TIMESTAMP
    # --------------------------------------------------------

    _validate_timestamp(
        headers["webhook-timestamp"],
        tolerance_seconds,
    )

    # --------------------------------------------------------
    # 4. LOAD SIGNING SECRET
    # --------------------------------------------------------

    secret = get_yoco_webhook_secret()

    # --------------------------------------------------------
    # 5. INITIALIZE OFFICIAL SVIX VERIFIER
    # --------------------------------------------------------

    try:

        webhook = Webhook(
            secret
        )

    except Exception as exc:

        current_app.logger.error(
            "Yoco webhook verifier initialization failed."
        )

        raise YocoWebhookError(
            "Could not initialize Yoco webhook verifier."
        ) from exc

    # --------------------------------------------------------
    # 6. VERIFY CRYPTOGRAPHIC SIGNATURE
    # --------------------------------------------------------

    try:

        webhook.verify(
            body,
            headers,
        )

    except WebhookVerificationError as exc:

        current_app.logger.warning(
            "Yoco webhook signature verification failed."
        )

        raise YocoWebhookError(
            "Webhook signature verification failed."
        ) from exc

    except Exception as exc:

        current_app.logger.error(
            "Unexpected Yoco webhook verification error."
        )

        raise YocoWebhookError(
            "Webhook verification failed."
        ) from exc

    # --------------------------------------------------------
    # 7. SUCCESS
    # --------------------------------------------------------

    current_app.logger.info(
        "Yoco webhook signature verified successfully."
    )

    return True
