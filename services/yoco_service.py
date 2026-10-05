import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from urllib import error, request

YOCO_API_BASE = "https://payments.yoco.com/api"
WEBHOOK_TOLERANCE_SECONDS = 180


class YocoError(RuntimeError):
    pass


def _secret_key():
    value = os.getenv("YOCO_SECRET_KEY", "").strip()
    if not value:
        raise YocoError("YOCO_SECRET_KEY is not configured.")
    return value


def _webhook_secret():
    value = os.getenv("YOCO_WEBHOOK_SECRET", "").strip()
    if not value:
        raise YocoError("YOCO_WEBHOOK_SECRET is not configured.")
    return value


def _api_request(method, path, payload=None, idempotency_key=None):
    body = None
    headers = {
        "Authorization": f"Bearer {_secret_key()}",
        "Accept": "application/json",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    req = request.Request(
        f"{YOCO_API_BASE}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise YocoError(f"Yoco API returned HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise YocoError(f"Could not reach Yoco: {exc.reason}") from exc


def create_checkout( *, amount_cents, success_url, cancel_url, failure_url, metadata, description):
    payload = {
        "amount": int(amount_cents),
        "currency": "ZAR",
        "successUrl": success_url,
        "cancelUrl": cancel_url,
        "failureUrl": failure_url,
        "metadata": {str(k): str(v) for k, v in metadata.items()},
        "lineItems": [
            {
                "displayName": description,
                "quantity": 1,
                "pricingDetails": {
                    "price": int(amount_cents),
                },
            }
        ],
    }
    return _api_request(
        "POST",
        "/checkouts",
        payload=payload,
        idempotency_key=str(uuid.uuid4()),
    )


def get_checkout(checkout_id):
    return _api_request("GET", f"/checkouts/{checkout_id}")


def _decode_webhook_secret(secret):
    if secret.startswith("whsec_"):
        secret = secret[len("whsec_"):]
    try:
        return base64.b64decode(secret)
    except Exception as exc:
        raise YocoError("YOCO_WEBHOOK_SECRET is invalid.") from exc


def verify_webhook(raw_body, headers):
    webhook_id = headers.get("webhook-id", "")
    timestamp = headers.get("webhook-timestamp", "")
    signature_header = headers.get("webhook-signature", "")

    if not webhook_id or not timestamp or not signature_header:
        return False

    try:
        timestamp_int = int(timestamp)
    except (TypeError, ValueError):
        return False

    if abs(int(time.time()) - timestamp_int) > WEBHOOK_TOLERANCE_SECONDS:
        return False

    signed_content = (
        webhook_id.encode("utf-8")
        + b"."
        + timestamp.encode("utf-8")
        + b"."
        + raw_body
    )
    digest = hmac.new(
        _decode_webhook_secret(_webhook_secret()),
        signed_content,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")

    # Standard webhook signatures can contain multiple versions/signatures.
    candidates = []
    for part in signature_header.split(" "):
        part = part.strip()
        if not part:
            continue
        if "," in part:
            version, value = part.split(",", 1)
            if version == "v1":
                candidates.append(value)
        else:
            candidates.append(part)

    return any(hmac.compare_digest(expected, value) for value in candidates)
