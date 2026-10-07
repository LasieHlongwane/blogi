# ============================================================
# CREATOR PLATFORM
# YOCO PAYMENT SERVICE
# ============================================================

import uuid

import requests

from flask import (
    current_app,
)


# ============================================================
# EXCEPTIONS
# ============================================================

class YocoError(Exception):
    """
    Raised when communication with Yoco fails or Yoco returns
    an invalid checkout response.
    """

    pass


# ============================================================
# HELPERS
# ============================================================

def get_yoco_secret_key():

    secret_key = current_app.config.get(
        "YOCO_SECRET_KEY"
    )

    if not secret_key:

        raise YocoError(
            "Yoco payments are not configured."
        )

    return secret_key


def get_yoco_checkout_url():

    return current_app.config.get(
        "YOCO_CHECKOUT_URL",
        "https://payments.yoco.com/api/checkouts",
    )


def generate_checkout_reference():

    return (
        "creator_"
        + uuid.uuid4().hex
    )


# ============================================================
# CREATE CHECKOUT
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

    # --------------------------------------------------------
    # VALIDATE AMOUNT
    # --------------------------------------------------------

    amount_cents = int(
        amount_cents
    )

    if amount_cents <= 0:

        raise YocoError(
            "Invalid checkout amount."
        )

    # --------------------------------------------------------
    # SECRET
    # --------------------------------------------------------

    secret_key = (
        get_yoco_secret_key()
    )

    # --------------------------------------------------------
    # LOCAL REFERENCE
    # --------------------------------------------------------

    checkout_reference = (
        generate_checkout_reference()
    )

    # --------------------------------------------------------
    # PAYLOAD
    # --------------------------------------------------------
    #
    # Prices are supplied by our backend.
    #
    # The browser does NOT determine:
    #
    #     amount
    #     currency
    #     creator ID
    #     plan price
    #
    # --------------------------------------------------------

    payload = {
        "amount": amount_cents,
        "currency": "ZAR",

        "successUrl": success_url,
        "cancelUrl": cancel_url,
        "failureUrl": failure_url,

        "clientReferenceId": (
            checkout_reference
        ),

        "externalId": (
            checkout_reference
        ),

        "metadata": {
            "creatorAccountId": str(
                creator.id
            ),
            "creatorUsername": str(
                creator.username
            ),
            "plan": str(
                plan
            ),
            "checkoutReference": (
                checkout_reference
            ),
        },
    }

    # --------------------------------------------------------
    # HEADERS
    # --------------------------------------------------------

    headers = {
        "Authorization": (
            f"Bearer {secret_key}"
        ),
        "Content-Type": (
            "application/json"
        ),
        "Idempotency-Key": (
            checkout_reference
        ),
    }

    # --------------------------------------------------------
    # REQUEST
    # --------------------------------------------------------

    try:

        response = requests.post(
            get_yoco_checkout_url(),
            json=payload,
            headers=headers,
            timeout=30,
        )

    except requests.RequestException as exc:

        current_app.logger.exception(
            "Unable to connect to Yoco."
        )

        raise YocoError(
            "Unable to connect to Yoco."
        ) from exc

    # --------------------------------------------------------
    # PARSE RESPONSE
    # --------------------------------------------------------

    try:

        data = response.json()

    except ValueError as exc:

        current_app.logger.error(
            "Yoco returned a non-JSON response. "
            "HTTP status=%s",
            response.status_code,
        )

        raise YocoError(
            "Yoco returned an invalid response."
        ) from exc

    # --------------------------------------------------------
    # ERROR RESPONSE
    # --------------------------------------------------------

    if not response.ok:

        # Do not log the secret key.
        # Do not expose the entire provider response to users.

        current_app.logger.error(
            "Yoco checkout creation failed. "
            "HTTP status=%s response=%s",
            response.status_code,
            data,
        )

        raise YocoError(
            "Yoco could not create the payment checkout."
        )

    # --------------------------------------------------------
    # REQUIRED RESPONSE FIELDS
    # --------------------------------------------------------

    checkout_id = data.get(
        "id"
    )

    redirect_url = data.get(
        "redirectUrl"
    )

    if not checkout_id:

        current_app.logger.error(
            "Yoco checkout response did not contain an ID."
        )

        raise YocoError(
            "Yoco returned an invalid checkout."
        )

    if not redirect_url:

        current_app.logger.error(
            "Yoco checkout response did not contain "
            "a redirectUrl."
        )

        raise YocoError(
            "Yoco did not return a payment URL."
        )

    # --------------------------------------------------------
    # RETURN NORMALIZED CHECKOUT
    # --------------------------------------------------------

    return {
        "id": checkout_id,

        "redirect_url": redirect_url,

        "status": data.get(
            "status"
        ),

        "amount": data.get(
            "amount"
        ),

        "currency": data.get(
            "currency"
        ),

        "processing_mode": data.get(
            "processingMode"
        ),

        "checkout_reference": (
            checkout_reference
        ),

        "raw": data,
    }
