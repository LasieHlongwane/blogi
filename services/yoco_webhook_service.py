# ============================================================
# CREATOR PLATFORM
# YOCO WEBHOOK SERVICE
# ============================================================
#
# Yoco webhook deliveries are sent using Svix.
#
# Signature verification is delegated to the official Svix
# Python library instead of manually implementing the signing
# algorithm.
#
# IMPORTANT:
#
# The webhook signing secret is:
#
#     YOCO_WEBHOOK_SECRET
#
# It is NOT:
#
#     YOCO_SECRET_KEY
#     YOCO_API_KEY
#
# ============================================================

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
    Return the Yoco/Svix webhook signing secret.

    The value must be the signing secret returned when the
    Yoco webhook subscription was created.

    Expected format:

        whsec_...

    This is NOT:

        YOCO_SECRET_KEY
        YOCO_API_KEY
    """

    secret = current_app.config.get(
        "YOCO_WEBHOOK_SECRET"
    )

    # ========================================================
    # VALIDATE CONFIGURATION
    # ========================================================

    if not secret:

        raise YocoWebhookError(
            "Yoco webhook secret is not configured."
        )

    if not isinstance(
        secret,
        str,
    ):

        raise YocoWebhookError(
            "Yoco webhook secret is invalid."
        )

    secret = secret.strip()

    if not secret:

        raise YocoWebhookError(
            "Yoco webhook secret is empty."
        )

    # ========================================================
    # EXPECT SVIX SECRET FORMAT
    # ========================================================

    if not secret.startswith(
        "whsec_"
    ):

        raise YocoWebhookError(
            "Yoco webhook secret has an invalid format."
        )

    return secret


# ============================================================
# NORMALIZE RAW BODY
# ============================================================

def _normalize_raw_body(
    raw_body,
):
    """
    Ensure the exact webhook body is represented as bytes.

    Signature verification must use the original request body.

    Do not:

        parse JSON
        serialize JSON again
        modify whitespace
        modify encoding

    before verification.
    """

    if raw_body is None:

        raise YocoWebhookError(
            "Webhook body is missing."
        )

    # --------------------------------------------------------
    # STRING
    # --------------------------------------------------------

    if isinstance(
        raw_body,
        str,
    ):

        try:

            return raw_body.encode(
                "utf-8"
            )

        except UnicodeEncodeError as exc:

            raise YocoWebhookError(
                "Webhook body could not be encoded."
            ) from exc

    # --------------------------------------------------------
    # BYTEARRAY
    # --------------------------------------------------------

    if isinstance(
        raw_body,
        bytearray,
    ):

        return bytes(
            raw_body
        )

    # --------------------------------------------------------
    # BYTES
    # --------------------------------------------------------

    if isinstance(
        raw_body,
        bytes,
    ):

        return raw_body

    # --------------------------------------------------------
    # INVALID TYPE
    # --------------------------------------------------------

    raise YocoWebhookError(
        "Webhook body must be raw bytes."
    )


# ============================================================
# VALIDATE REQUIRED HEADERS
# ============================================================

def _validate_headers(
    *,
    webhook_id,
    webhook_timestamp,
    webhook_signature,
):
    """
    Validate that all Svix signature headers were supplied.
    """

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


# ============================================================
# VERIFY WEBHOOK
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
    Verify a Yoco webhook using the official Svix verifier.

    Parameters are deliberately kept compatible with the
    existing payments route:

        verify_yoco_webhook(
            raw_body=raw_body,
            webhook_id=webhook_id,
            webhook_timestamp=webhook_timestamp,
            webhook_signature=webhook_signature,
        )

    The function returns True when the webhook signature is
    valid.

    It raises YocoWebhookError when verification fails.
    """

    # ========================================================
    # REQUIRED HEADERS
    # ========================================================

    _validate_headers(
        webhook_id=webhook_id,
        webhook_timestamp=webhook_timestamp,
        webhook_signature=webhook_signature,
    )

    # ========================================================
    # RAW REQUEST BODY
    # ========================================================

    raw_body = _normalize_raw_body(
        raw_body
    )

    # ========================================================
    # WEBHOOK SECRET
    # ========================================================

    secret = (
        get_yoco_webhook_secret()
    )

    # ========================================================
    # CREATE SVIX VERIFIER
    # ========================================================

    try:

        webhook = Webhook(
            secret
        )

    except Exception as exc:

        raise YocoWebhookError(
            "Could not initialize Yoco webhook verifier."
        ) from exc

    # ========================================================
    # SVIX HEADERS
    # ========================================================
    #
    # Svix expects these headers:
    #
    #     webhook-id
    #     webhook-timestamp
    #     webhook-signature
    #
    # Header names are case-insensitive over HTTP, but we
    # explicitly supply the canonical Svix names here.
    #
    # ========================================================

    headers = {
        "webhook-id": str(
            webhook_id
        ),
        "webhook-timestamp": str(
            webhook_timestamp
        ),
        "webhook-signature": str(
            webhook_signature
        ),
    }

    # ========================================================
    # VERIFY
    # ========================================================
    #
    # The official Svix verifier handles:
    #
    #     secret decoding
    #     signature parsing
    #     HMAC verification
    #     timestamp verification
    #     multiple signatures
    #
    # We deliberately do NOT manually calculate an HMAC here.
    #
    # ========================================================

    try:

        webhook.verify(
            raw_body,
            headers,
        )

    except WebhookVerificationError as exc:

        raise YocoWebhookError(
            "Webhook signature verification failed."
        ) from exc

    except Exception as exc:

        # Do not leak signature/header/secret information
        # through application logs.

        raise YocoWebhookError(
            "Webhook verification failed."
        ) from exc

    # ========================================================
    # VERIFIED
    # ========================================================

    return True
