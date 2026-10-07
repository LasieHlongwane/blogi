# ============================================================
# CREATOR PLATFORM
# YOCO API SERVICE
# ============================================================

import requests

from flask import current_app


# ============================================================
# EXCEPTION
# ============================================================

class YocoAPIError(Exception):
    pass


# ============================================================
# CONFIG
# ============================================================

def get_yoco_api_key():

    api_key = current_app.config.get(
        "YOCO_API_KEY"
    )

    if not api_key:

        raise YocoAPIError(
            "YOCO_API_KEY is not configured."
        )

    return api_key


def get_yoco_api_base_url():

    return (
        current_app.config.get(
            "YOCO_API_BASE_URL",
            "https://api.yoco.com",
        )
        .rstrip("/")
    )


# ============================================================
# FETCH PAYMENT
# ============================================================

def fetch_payment(
    payment_id,
):

    if not payment_id:

        raise YocoAPIError(
            "Payment ID is required."
        )

    url = (
        f"{get_yoco_api_base_url()}"
        f"/v1/payments/{payment_id}/"
    )

    headers = {
        "Authorization": (
            f"Bearer {get_yoco_api_key()}"
        ),
        "Accept": "application/json",
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=30,
        )

    except requests.RequestException as exc:

        current_app.logger.exception(
            "Unable to connect to Yoco API."
        )

        raise YocoAPIError(
            "Unable to fetch payment from Yoco."
        ) from exc

    try:

        data = response.json()

    except ValueError as exc:

        current_app.logger.error(
            (
                "Yoco Fetch Payment returned "
                "non-JSON. status=%s"
            ),
            response.status_code,
        )

        raise YocoAPIError(
            "Yoco returned an invalid payment response."
        ) from exc

    if not response.ok:

        current_app.logger.error(
            (
                "Yoco Fetch Payment failed. "
                "payment_id=%s status=%s response=%s"
            ),
            payment_id,
            response.status_code,
            data,
        )

        raise YocoAPIError(
            "Yoco could not verify the payment."
        )

    return data
