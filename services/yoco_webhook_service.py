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

    # ========================================================
    # TEMPORARY SAFE DEBUGGING
    # ========================================================
    #
    # IMPORTANT:
    #
    # This does NOT print the webhook secret.
    #
    # It only tells us:
    #
    #   1. Whether Flask loaded a value.
    #   2. Whether it begins with "whsec_".
    #   3. The total character length.
    #
    # Remove this diagnostic once webhook verification works.
    #
    # ========================================================

    current_app.logger.warning(
        "YOCO_WEBHOOK_SECRET loaded=%s prefix=%s length=%s",
        bool(secret),
        secret[:6] if isinstance(secret, str) else None,
        len(secret) if isinstance(secret, str) else 0,
    )

    # ========================================================
    # VALIDATE SECRET
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

    # ========================================================
    # REMOVE WHSEC PREFIX
    # ========================================================

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

    # ========================================================
    # BASE64 PADDING
    # ========================================================
    #
    # Base64 strings should normally already contain the
    # correct padding.
    #
    # Adding missing padding also allows us to handle secrets
    # where trailing "=" characters were omitted.
    #
    # ========================================================

    missing_padding = (
        -len(encoded_secret)
    ) % 4

    if missing_padding:

        encoded_secret += (
            "=" * missing_padding
        )

    # ========================================================
    # BASE64 DECODE
    # ========================================================

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
    Extract v1 signatures from the Svix webhook-signature
    header.

    Example:

        v1,abc123... v1,xyz456...

    During signing-secret rotation Svix can include more than
    one signature.

    We only accept v1 signatures.
    """

    if not signature_header:

        return []

    signatures = []

    # ========================================================
    # SPLIT SIGNATURE HEADER
    # ========================================================

    for item in signature_header.split():

        item = item.strip()

        if not item:

            continue

        if "," not in item:

            continue

        # ----------------------------------------------------
        # FORMAT:
        #
        #     v1,<base64-signature>
        #
        # ----------------------------------------------------

        version, signature = item.split(
            ",",
            1,
        )

        version = version.strip()
        signature = signature.strip()

        # ----------------------------------------------------
        # ONLY ACCEPT VERSION 1
        # ----------------------------------------------------

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

    # --------------------------------------------------------
    # Convert string body to UTF-8 bytes if necessary.
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Ensure immutable bytes.
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # REPLAY PROTECTION
    # --------------------------------------------------------

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
    # We must use the exact HTTP request body received from
    # Yoco/Svix.
    #
    # Do NOT:
    #
    #   request.get_json()
    #   json.dumps(...)
    #
    # and then use that regenerated JSON for signature
    # verification.
    #
    # Changing spaces, ordering or encoding would change the
    # signature.
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
    # GET SIGNATURES PROVIDED BY YOCO / SVIX
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
    #
    # Never use:
    #
    #     expected_signature == supplied_signature
    #
    # for authentication signatures.
    #
    # hmac.compare_digest() avoids timing differences that
    # could leak signature information.
    #
    # ========================================================

    for supplied_signature in supplied_signatures:

        if hmac.compare_digest(
            expected_signature,
            supplied_signature,
        ):

            return True

    # ========================================================
    # FAILED VERIFICATION
    # ========================================================

    raise YocoWebhookError(
        "Webhook signature verification failed."
    )
