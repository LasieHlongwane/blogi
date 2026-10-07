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

import time

from flask import (
    current_app,
    request,
)

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
    Validate that all required Svix signature headers exist.
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
# SAFE DIAGNOSTIC LOGGING
# ============================================================

def _log_safe_diagnostics(
    *,
    raw_body,
    webhook_id,
    webhook_timestamp,
    webhook_signature,
):
    """
    Log non-secret information about the incoming webhook.

    SECURITY:

    We deliberately DO NOT log:

        YOCO_WEBHOOK_SECRET
        webhook-signature value
        raw webhook body
        Authorization headers
        API keys

    These diagnostics are temporary and should be removed
    once webhook verification is working.
    """

    # ========================================================
    # TIMESTAMP AGE
    # ========================================================

    timestamp_age = None

    try:

        timestamp_value = int(
            webhook_timestamp
        )

        timestamp_age = (
            int(
                time.time()
            )
            - timestamp_value
        )

    except (
        TypeError,
        ValueError,
    ):

        timestamp_age = None

    # ========================================================
    # SIGNATURE METADATA
    # ========================================================
    #
    # We only log whether the signature exists and the number
    # of signature entries.
    #
    # We DO NOT log the actual signature.
    #
    # ========================================================

    signature_present = bool(
        webhook_signature
    )

    signature_count = 0

    if webhook_signature:

        signature_count = len(
            [
                item
                for item
                in str(
                    webhook_signature
                ).split()
                if item.strip()
            ]
        )

    # ========================================================
    # REQUEST METADATA
    # ========================================================

    content_type = request.headers.get(
        "Content-Type",
        "",
    )

    user_agent = request.headers.get(
        "User-Agent",
        "",
    )

    content_length = request.headers.get(
        "Content-Length",
        "",
    )

    # ========================================================
    # LOG
    # ========================================================

    current_app.logger.warning(
        (
            "Yoco webhook diagnostic: "
            "webhook_id=%s "
            "timestamp_present=%s "
            "timestamp_age_seconds=%s "
            "signature_present=%s "
            "signature_count=%s "
            "body_length=%s "
            "content_length=%s "
            "content_type=%s "
            "user_agent=%s"
        ),
        webhook_id,
        bool(
            webhook_timestamp
        ),
        timestamp_age,
        signature_present,
        signature_count,
        len(
            raw_body
        ),
        content_length,
        content_type,
        user_agent,
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

    NOTE:

    tolerance_seconds remains in the function signature for
    compatibility with the previous implementation.

    Timestamp/replay validation is performed by the official
    Svix verifier.
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
    # SAFE DIAGNOSTICS
    # ========================================================

    _log_safe_diagnostics(
        raw_body=raw_body,
        webhook_id=webhook_id,
        webhook_timestamp=webhook_timestamp,
        webhook_signature=webhook_signature,
    )

    # ========================================================
    # WEBHOOK SECRET
    # ========================================================

    secret = (
        get_yoco_webhook_secret()
    )

    # ========================================================
    # SAFE SECRET CONFIGURATION CHECK
    # ========================================================
    #
    # We deliberately DO NOT log:
    #
    #     secret
    #     secret prefix
    #     secret length
    #
    # We only confirm that configuration validation passed.
    #
    # ========================================================

    current_app.logger.warning(
        (
            "Yoco webhook diagnostic: "
            "webhook signing secret configuration "
            "loaded successfully."
        )
    )

    # ========================================================
    # CREATE SVIX VERIFIER
    # ========================================================

    try:

        webhook = Webhook(
            secret
        )

    except Exception as exc:

        current_app.logger.warning(
            (
                "Yoco webhook diagnostic: "
                "Svix verifier initialization failed. "
                "exception_type=%s"
            ),
            type(
                exc
            ).__name__,
        )

        raise YocoWebhookError(
            "Could not initialize Yoco webhook verifier."
        ) from exc

    # ========================================================
    # SVIX HEADERS
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

    try:

        webhook.verify(
            raw_body,
            headers,
        )

    except WebhookVerificationError as exc:

        # ----------------------------------------------------
        # SAFE FAILURE DIAGNOSTIC
        # ----------------------------------------------------
        #
        # We log only the exception class.
        #
        # We intentionally avoid logging str(exc) because
        # third-party verification libraries can change what
        # their exception messages contain.
        # ----------------------------------------------------

        current_app.logger.warning(
            (
                "Yoco webhook diagnostic: "
                "Svix signature verification rejected "
                "the request. exception_type=%s"
            ),
            type(
                exc
            ).__name__,
        )

        raise YocoWebhookError(
            "Webhook signature verification failed."
        ) from exc

    except Exception as exc:

        current_app.logger.warning(
            (
                "Yoco webhook diagnostic: "
                "Unexpected verification failure. "
                "exception_type=%s"
            ),
            type(
                exc
            ).__name__,
        )

        raise YocoWebhookError(
            "Webhook verification failed."
        ) from exc

    # ========================================================
    # VERIFIED
    # ========================================================

    current_app.logger.info(
        (
            "Yoco webhook signature verified "
            "successfully. webhook_id=%s"
        ),
        webhook_id,
    )

    return True
