
"""
KALXA CREATOR — YOCO CHECKOUT SERVICE

Creates secure Yoco checkouts for once-off creator
plan activations and upgrades.

Current pricing:
    Free:               R0
    Standard:            R300 once-off
    Premium:             R500 once-off
    Standard -> Premium: R200 once-off

Important:
- This service does not process fan payments.
- Paystack handles fan -> creator payments.
- Prices are determined by the server.
- Upgrade eligibility is checked by routes/payments.py.
- Yoco webhooks must independently verify payments.
"""

import uuid

from urllib.parse import urlparse

import requests

from flask import current_app

from config import (
    PLAN_PRICES_CENTS,
    STANDARD_TO_PREMIUM_UPGRADE_CENTS,
)


# ============================================================
# EXCEPTIONS
# ============================================================

class YocoError(Exception):
    """
    Raised when a Yoco checkout cannot be created
    or validated.
    """

    pass


# ============================================================
# YOCO CONFIGURATION
# ============================================================

def get_yoco_secret_key():
    """
    Retrieve the Yoco secret key from Flask configuration.
    """

    key = current_app.config.get(
        "YOCO_SECRET_KEY"
    )

    if not isinstance(key, str) or not key.strip():
        raise YocoError(
            "Yoco payments are not configured."
        )

    return key.strip()


def get_yoco_checkout_url():
    """
    Return the configured Yoco checkout endpoint.
    """

    checkout_url = current_app.config.get(
        "YOCO_CHECKOUT_URL",
        "https://payments.yoco.com/api/checkouts",
    )

    if not isinstance(checkout_url, str):
        raise YocoError(
            "Invalid Yoco checkout configuration."
        )

    checkout_url = checkout_url.strip()

    parsed = urlparse(checkout_url)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise YocoError(
            "Yoco checkout endpoint must use HTTPS."
        )

    # Avoid sending payment credentials to an
    # unintended host through misconfiguration.
    if parsed.hostname != "payments.yoco.com":
        raise YocoError(
            "Untrusted Yoco checkout endpoint."
        )

    return checkout_url


# ============================================================
# CHECKOUT REFERENCES
# ============================================================

def generate_checkout_reference():
    """
    Generate a unique reference for each checkout.
    """

    return (
        "creator_"
        + uuid.uuid4().hex
    )


# ============================================================
# RETURN URL VALIDATION
# ============================================================

def validate_return_url(target):
    """
    Validate the HTTPS return URL and ensure it
    belongs to the configured Kalxa website.
    """

    if not isinstance(target, str):
        raise YocoError(
            "Invalid payment return URL."
        )

    parsed = urlparse(target)

    site_url = str(
        current_app.config.get("SITE_URL") or ""
    ).rstrip("/")

    site_parsed = urlparse(site_url)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or site_parsed.scheme != "https"
        or not site_parsed.hostname
        or parsed.netloc != site_parsed.netloc
    ):
        raise YocoError(
            "A secure Kalxa return URL is required."
        )

    return target


# ============================================================
# PLAN AND AMOUNT VALIDATION
# ============================================================

def validate_checkout_amount(
    *,
    amount_cents,
    plan,
):
    """
    Validate an activation or upgrade amount.

    Supported:
        Standard activation: R300
        Premium activation:  R500
        Premium upgrade:     R200

    This helper validates amount/plan combinations.
    It does not independently authorize an upgrade.
    """

    if type(amount_cents) is not int:
        raise YocoError(
            "Checkout amount must be an integer "
            "number of cents."
        )

    if amount_cents <= 0:
        raise YocoError(
            "Checkout amount must be positive."
        )

    if plan not in (
        "standard",
        "premium",
    ):
        raise YocoError(
            "Invalid activation plan."
        )

    standard_price = (
        PLAN_PRICES_CENTS["standard"]
    )

    premium_price = (
        PLAN_PRICES_CENTS["premium"]
    )

    upgrade_price = (
        STANDARD_TO_PREMIUM_UPGRADE_CENTS
    )

    valid_amounts = {
        "standard": {
            standard_price,
        },
        "premium": {
            premium_price,
            upgrade_price,
        },
    }

    if amount_cents not in valid_amounts[plan]:
        raise YocoError(
            "Invalid activation or upgrade amount."
        )

    return True


# ============================================================
# CREATOR VALIDATION
# ============================================================

def validate_creator(creator):
    """
    Ensure the checkout is linked to a valid creator.
    """

    if creator is None:
        raise YocoError(
            "Creator account is required."
        )

    creator_id = getattr(
        creator,
        "id",
        None,
    )

    if (
        isinstance(creator_id, bool)
        or not isinstance(creator_id, int)
        or creator_id <= 0
    ):
        raise YocoError(
            "Invalid creator account."
        )

    username = getattr(
        creator,
        "username",
        None,
    )

    if not username:
        raise YocoError(
            "Creator username is required."
        )

    if getattr(
        creator,
        "account_status",
        None,
    ) in (
        "suspended",
        "rejected",
    ):
        raise YocoError(
            "This creator cannot purchase a plan."
        )

    return True


# ============================================================
# CREATE YOCO CHECKOUT
# ============================================================

def create_checkout(
    *,
    amount_cents,
    creator,
    plan,
    success_url,
    cancel_url,
    failure_url,
):
    """
    Create a secure Yoco checkout.

    Called by:
        routes/payments.py

    The caller determines the amount using the
    creator's plan and verified payment history.

    This service performs independent validation
    of the amount/plan combination.

    Returns:
        {
            "id": checkout_id,
            "redirect_url": checkout_url,
            "status": ...,
            "amount": ...,
            "currency": ...,
            "processing_mode": ...,
            "checkout_reference": ...,
            "raw": ...
        }
    """

    # --------------------------------------------------------
    # 1. VALIDATE CREATOR
    # --------------------------------------------------------

    validate_creator(
        creator
    )

    # --------------------------------------------------------
    # 2. VALIDATE PLAN AND AMOUNT
    # --------------------------------------------------------

    validate_checkout_amount(
        amount_cents=amount_cents,
        plan=plan,
    )

    # --------------------------------------------------------
    # 3. VALIDATE RETURN URLS
    # --------------------------------------------------------

    success_url = validate_return_url(
        success_url
    )

    cancel_url = validate_return_url(
        cancel_url
    )

    failure_url = validate_return_url(
        failure_url
    )

    # --------------------------------------------------------
    # 4. GENERATE REFERENCE
    # --------------------------------------------------------

    reference = (
        generate_checkout_reference()
    )

    # --------------------------------------------------------
    # 5. IDENTIFY PAYMENT TYPE
    # --------------------------------------------------------

    if (
        plan == "premium"
        and amount_cents
        == STANDARD_TO_PREMIUM_UPGRADE_CENTS
    ):

        payment_type = (
            "standard_to_premium_upgrade"
        )

    else:

        payment_type = (
            "plan_activation"
        )

    # --------------------------------------------------------
    # 6. BUILD YOCO REQUEST
    # --------------------------------------------------------

    payload = {
        "amount": amount_cents,
        "currency": "ZAR",

        "successUrl": success_url,
        "cancelUrl": cancel_url,
        "failureUrl": failure_url,

        "clientReferenceId": reference,
        "externalId": reference,

        "metadata": {
            "creatorAccountId": str(
                creator.id
            ),
            "creatorUsername": str(
                creator.username
            ),
            "plan": plan,
            "paymentType": payment_type,
            "checkoutReference": reference,
        },
    }

    # --------------------------------------------------------
    # 7. AUTHENTICATION HEADERS
    # --------------------------------------------------------

    headers = {
        "Authorization": (
            f"Bearer {get_yoco_secret_key()}"
        ),
        "Content-Type": (
            "application/json"
        ),
        "Idempotency-Key": reference,
    }

    # --------------------------------------------------------
    # 8. REQUEST YOCO CHECKOUT
    # --------------------------------------------------------

    try:

        response = requests.post(
            get_yoco_checkout_url(),
            json=payload,
            headers=headers,
            timeout=30,
        )

        data = response.json()

    except (
        requests.RequestException,
        ValueError,
    ) as exc:

        current_app.logger.exception(
            "Yoco checkout communication failed"
        )

        raise YocoError(
            "Yoco checkout is temporarily unavailable."
        ) from exc

    # --------------------------------------------------------
    # 9. VALIDATE YOCO RESPONSE
    # --------------------------------------------------------

    if (
        not response.ok
        or not isinstance(data, dict)
    ):

        current_app.logger.error(
            "Yoco checkout failed: HTTP %s",
            response.status_code,
        )

        raise YocoError(
            "Yoco could not create a checkout."
        )

    checkout_id = data.get(
        "id"
    )

    redirect_url = data.get(
        "redirectUrl"
    )

    if (
        not isinstance(checkout_id, str)
        or not checkout_id.strip()
    ):

        raise YocoError(
            "Yoco returned no checkout ID."
        )

    if (
        not isinstance(redirect_url, str)
        or not redirect_url.strip()
    ):

        raise YocoError(
            "Yoco returned no checkout URL."
        )

    parsed_redirect = urlparse(
        redirect_url
    )

    if (
        parsed_redirect.scheme != "https"
        or not parsed_redirect.hostname
        or parsed_redirect.username
        or parsed_redirect.password
    ):

        raise YocoError(
            "Yoco returned an insecure checkout URL."
        )

    # --------------------------------------------------------
    # 10. VERIFY RESPONSE AMOUNT
    # --------------------------------------------------------

    provider_amount = data.get(
        "amount"
    )

    if provider_amount is not None:

        if (
            type(provider_amount) is not int
            or provider_amount != amount_cents
        ):

            raise YocoError(
                "Yoco returned an unexpected amount."
            )

    # --------------------------------------------------------
    # 11. VERIFY CURRENCY
    # --------------------------------------------------------

    provider_currency = data.get(
        "currency"
    )

    if (
        provider_currency is not None
        and provider_currency != "ZAR"
    ):

        raise YocoError(
            "Yoco returned an unexpected currency."
        )

    # --------------------------------------------------------
    # 12. RETURN CHECKOUT DATA
    # --------------------------------------------------------

    return {
        "id": checkout_id.strip(),
        "redirect_url": redirect_url,
        "status": data.get(
            "status"
        ),
        "amount": provider_amount,
        "currency": provider_currency,
        "processing_mode": data.get(
            "processingMode"
        ),
        "checkout_reference": reference,
        "payment_type": payment_type,
        "raw": data,
    }
