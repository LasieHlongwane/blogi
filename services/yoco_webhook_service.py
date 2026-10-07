# ============================================================
# CREATOR PLATFORM
# YOCO WEBHOOK SERVICE
# ============================================================

import base64
import hashlib
import hmac
import time

from flask import current_app


# ============================================================
# EXCEPTION
# ============================================================

class YocoWebhookError(Exception):
    pass


# ============================================================
# WEBHOOK SECRET
# ============================================================

def get_yoco_webhook_secret():

    secret = current_app.config.get(
        "YOCO_WEBHOOK_SECRET"
    )

    if not secret:

        raise YocoWebhookError(
            "Yoco webhook secret is not configured."
        )

    return secret


# ============================================================
# NORMALIZE SECRET
# ============================================================

def _decode_webhook_secret(secret):

    secret = (
        secret
        .strip()
    )

    # Yoco/Svix-style webhook secrets commonly use a
    # whsec_ prefix followed by Base64 key material.
    if secret.startswith(
        "whsec_"
    ):

        encoded = secret[
            len("whsec_"):
        ]

        try:

            return base64.b64decode(
                encoded
            )

        except Exception as exc:

            raise YocoWebhookError(
                "Invalid Yoco webhook secret."
            ) from exc

    return secret.encode(
        "utf-8"
    )


# ============================================================
# SIGNATURE PARSING
# ============================================================

def _extract_signatures(
    signature_header,
):

    signatures = []

    for item in (
        signature_header
        .split()
    ):

        if "," in item:

            parts = item.split(
                ",",
                1,
            )

            if len(parts) == 2:
                signatures.append(
                    parts[1]
                )

            continue

        # Some providers may send only the Base64 signature.
        if item:
            signatures.append(
                item
            )

    return signatures


# ============================================================
# VERIFY WEBHOOK
# ============================================================

def verify_yoco_webhook(
    *,
    raw_body,
    webhook_id,
    webhook_timestamp,
    webhook_signature,
    tolerance_seconds=180,
):

    if not webhook_id:

        raise YocoWebhookError(
            "Missing webhook-id header."
        )

    if not webhook_timestamp:

        raise YocoWebhookError(
            "Missing webhook-timestamp header."
        )

    if not webhook_signature:

        raise YocoWebhookError(
            "Missing webhook-signature header."
        )

    # --------------------------------------------------------
    # TIMESTAMP
    # --------------------------------------------------------

    try:

        timestamp = int(
            webhook_timestamp
        )

    except (TypeError, ValueError) as exc:

        raise YocoWebhookError(
            "Invalid webhook timestamp."
        ) from exc

    now = int(
        time.time()
    )

    if abs(
        now - timestamp
    ) > tolerance_seconds:

        raise YocoWebhookError(
            "Webhook timestamp is outside "
            "the allowed tolerance."
        )

    # --------------------------------------------------------
    # SIGNED PAYLOAD
    # --------------------------------------------------------

    try:

        body_text = raw_body.decode(
            "utf-8"
        )

    except UnicodeDecodeError as exc:

        raise YocoWebhookError(
            "Webhook body is not valid UTF-8."
        ) from exc

    signed_content = (
        f"{webhook_id}."
        f"{webhook_timestamp}."
        f"{body_text}"
    )

    # --------------------------------------------------------
    # HMAC SHA256
    # --------------------------------------------------------

    key = _decode_webhook_secret(
        get_yoco_webhook_secret()
    )

    digest = hmac.new(
        key,
        signed_content.encode(
            "utf-8"
        ),
        hashlib.sha256,
    ).digest()

    expected_signature = (
        base64.b64encode(
            digest
        )
        .decode(
            "utf-8"
        )
    )

    supplied_signatures = (
        _extract_signatures(
            webhook_signature
        )
    )

    if not supplied_signatures:

        raise YocoWebhookError(
            "Webhook signature is invalid."
        )

    valid = any(
        hmac.compare_digest(
            expected_signature,
            supplied,
        )
        for supplied in supplied_signatures
    )

    if not valid:

        raise YocoWebhookError(
            "Webhook signature verification failed."
        )

    return True
