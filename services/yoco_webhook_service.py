# ============================================================
# CREATOR PLATFORM
# YOCO WEBHOOK SERVICE
# ============================================================

import base64
import binascii
import hashlib
import hmac
import time

from flask import current_app


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

    IMPORTANT:
    This must be the webhook secret returned when the Yoco
    webhook subscription was created.

    It is NOT:
        - YOCO_SECRET_KEY
        - YOCO_API_KEY
        - a Checkout API key
    """

    secret = current_app.config.get(
        "YOCO_WEBHOOK_SECRET"
    )

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

    return secret


# ============================================================
# DECODE WEBHOOK SECRET
# ============================================================

def _decode_webhook_secret(
    secret,
):
    """
    Svix webhook signing secrets normally look like:

        whsec_<base64-data>

    The whsec_ prefix must be removed and the remaining
    Base64 value decoded before it is used as the HMAC key.
    """

    secret = secret.strip()

    if secret.startswith(
        "whsec_"
    ):

        encoded_secret = secret[
            len("whsec_"):
        ]

    else:

        encoded_secret = secret

    if not encoded_secret:

        raise YocoWebhookError(
            "Yoco webhook secret contains no key material."
        )

    # --------------------------------------------------------
    # BASE64 PADDING
    # --------------------------------------------------------
    #
    # Base64 strings should normally already contain the
    # correct padding, but adding missing padding makes the
    # decoder tolerant of secrets where "=" characters were
    # omitted.
    # --------------------------------------------------------

    missing_padding = (
        -len(encoded_secret)
    ) % 4

    if missing_padding:

        encoded_secret += (
            "=" * missing_padding
        )

    try:

        return base64.b64decode(
            encoded_secret,
            validate=True,
        )

    except (
        binascii.Error,
        ValueError,
    ) as exc:

        raise YocoWebhookError(
            "Yoco webhook secret is not valid Base64."
        ) from exc


# ============================================================
# EXTRACT SVIX SIGNATURES
# ============================================================

def _extract_signatures(
    signature_header,
):
    """
    Svix may provide one or more signatures in the header.

    Example:

        v1,abc123... v1,xyz456...

    We only accept v1 signatures.
    """

    if not signature_header:

        return []

    signatures = []

    for item in signature_header.split():

        item = item.strip()

        if not item:

            continue

        if "," not in item:

            continue

        version, signature = item.split(
            ",",
            1,
        )

        version = version.strip()
        signature = signature.strip()

        if version != "v1":

            continue

        if not signature:

            continue

        signatures.append(
            signature
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
    tolerance_seconds=300,
):
    """
    Verify a Yoco webhook using the Svix signing scheme.

    Signed content:

        webhook-id.webhook-timestamp.raw-body

    HMAC:

        HMAC-SHA256(
            decoded webhook secret,
            signed content
        )

    The resulting digest is Base64 encoded and compared
    against every v1 signature supplied by Svix.
    """

    # ========================================================
    # REQUIRED HEADERS
    # ========================================================

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

    # ========================================================
    # RAW BODY
    # ========================================================

    if raw_body is None:

        raise YocoWebhookError(
            "Webhook body is missing."
        )

    if isinstance(
        raw_body,
        str,
    ):

        raw_body = raw_body.encode(
            "utf-8"
        )

    if not isinstance(
        raw_body,
        (
            bytes,
            bytearray,
        ),
    ):

        raise YocoWebhookError(
            "Webhook body must be raw bytes."
        )

    # Convert bytearray to bytes if necessary.

    raw_body = bytes(
        raw_body
    )

    # ========================================================
    # TIMESTAMP
    # ========================================================

    try:

        timestamp = int(
            webhook_timestamp
        )

    except (
        TypeError,
        ValueError,
    ) as exc:

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

    # ========================================================
    # SIGNED CONTENT
    # ========================================================
    #
    # IMPORTANT:
    #
    # Do not parse JSON and serialize it again here.
    #
    # The signature was calculated from the exact HTTP body
    # Yoco/Svix sent.
    #
    # ========================================================

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

    # ========================================================
    # WEBHOOK SIGNING KEY
    # ========================================================

    secret = (
        get_yoco_webhook_secret()
    )

    signing_key = (
        _decode_webhook_secret(
            secret
        )
    )

    # ========================================================
    # CALCULATE EXPECTED SIGNATURE
    # ========================================================

    digest = hmac.new(
        signing_key,
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
            "ascii"
        )
    )

    # ========================================================
    # GET SUPPLIED SIGNATURES
    # ========================================================

    supplied_signatures = (
        _extract_signatures(
            webhook_signature
        )
    )

    if not supplied_signatures:

        raise YocoWebhookError(
            "No valid v1 webhook signatures were supplied."
        )

    # ========================================================
    # CONSTANT-TIME SIGNATURE COMPARISON
    # ========================================================

    for supplied_signature in supplied_signatures:

        if hmac.compare_digest(
            expected_signature,
            supplied_signature,
        ):

            return True

    # ========================================================
    # FAILED
    # ========================================================

    raise YocoWebhookError(
        "Webhook signature verification failed."
    )
