import hashlib
import hmac
import json
import os

import requests


PAYSTACK_BASE_URL = "https://api.paystack.co"


class PaystackError(Exception):
    pass


def get_paystack_secret_key():

    key = (
        os.getenv("PAYSTACK_SECRET_KEY", "")
        .strip()
    )

    if not key:

        raise PaystackError(
            "PAYSTACK_SECRET_KEY is not configured."
        )

    return key


def _headers():

    return {
        "Authorization": (
            f"Bearer {get_paystack_secret_key()}"
        ),
        "Content-Type": "application/json",
    }


def _request(
    method,
    path,
    *,
    json_data=None,
    params=None,
):

    url = (
        f"{PAYSTACK_BASE_URL}{path}"
    )

    try:

        response = requests.request(
            method,
            url,
            headers=_headers(),
            json=json_data,
            params=params,
            timeout=20,
        )

    except requests.RequestException as exc:

        raise PaystackError(
            "Could not connect to Paystack."
        ) from exc

    try:

        payload = response.json()

    except ValueError as exc:

        raise PaystackError(
            "Paystack returned an invalid response."
        ) from exc

    if (
        not response.ok
        or not payload.get("status")
    ):

        message = (
            payload.get("message")
            or "Paystack request failed."
        )

        raise PaystackError(
            message
        )

    return payload


# ============================================================
# BANKS
# ============================================================

def list_south_african_banks():

    payload = _request(
        "GET",
        "/bank",
        params={
            "country": "south africa",
            "currency": "ZAR",
            "perPage": 100,
        },
    )

    return (
        payload.get("data")
        or []
    )


# ============================================================
# CREATOR SUBACCOUNT
# ============================================================

def create_creator_subaccount(
    *,
    business_name,
    bank_code,
    account_number,
    creator_email=None,
    creator_name=None,
):

    data = {
        "business_name": business_name,
        "settlement_bank": bank_code,
        "account_number": account_number,

        # IMPORTANT:
        # Paystack defines percentage_charge as the
        # percentage received by the MAIN account.
        #
        # Kalxa takes 0% platform commission.
        "percentage_charge": 0,

        "description": (
            f"Creator payout account for "
            f"{business_name}"
        ),
    }

    if creator_email:

        data["primary_contact_email"] = (
            creator_email
        )

    if creator_name:

        data["primary_contact_name"] = (
            creator_name
        )

    payload = _request(
        "POST",
        "/subaccount",
        json_data=data,
    )

    return payload["data"]


def fetch_subaccount(
    subaccount_code,
):

    payload = _request(
        "GET",
        (
            "/subaccount/"
            f"{subaccount_code}"
        ),
    )

    return payload["data"]


# ============================================================
# FAN PAYMENT
# ============================================================

def initialize_fan_payment(
    *,
    email,
    amount_cents,
    reference,
    subaccount_code,
    callback_url,
    metadata,
):

    if amount_cents <= 0:

        raise PaystackError(
            "Payment amount must be greater than zero."
        )

    if not subaccount_code:

        raise PaystackError(
            "Creator payout account is not connected."
        )

    data = {
        "email": email,
        "amount": str(amount_cents),
        "currency": "ZAR",
        "reference": reference,
        "callback_url": callback_url,
        "subaccount": subaccount_code,

        # Creator receives the settlement.
        #
        # This also means processing charges are
        # borne by the creator's subaccount.
        "bearer": "subaccount",

        "metadata": json.dumps(
            metadata,
            separators=(",", ":"),
        ),
    }

    payload = _request(
        "POST",
        "/transaction/initialize",
        json_data=data,
    )

    return payload["data"]


# ============================================================
# VERIFY TRANSACTION
# ============================================================

def verify_transaction(
    reference,
):

    payload = _request(
        "GET",
        (
            "/transaction/verify/"
            f"{reference}"
        ),
    )

    return payload["data"]


# ============================================================
# WEBHOOK VERIFICATION
# ============================================================

def verify_paystack_webhook(
    raw_body,
    signature,
):

    if not signature:

        return False

    secret = (
        get_paystack_secret_key()
        .encode("utf-8")
    )

    expected = hmac.new(
        secret,
        raw_body,
        hashlib.sha512,
    ).hexdigest()

    return hmac.compare_digest(
        expected,
        signature,
    )

# ============================================================
# SOUTH AFRICAN PAYOUT ONBOARDING
# ============================================================

def list_south_african_banks(
    verification_only=True,
):

    params = {
        "currency": "ZAR",
        "country": "south africa",
        "perPage": 100,
    }

    if verification_only:

        params[
            "enabled_for_verification"
        ] = "true"

    payload = _request(
        "GET",
        "/bank",
        params=params,
    )

    banks = (
        payload.get("data")
        or []
    )

    banks.sort(
        key=lambda bank: (
            bank.get("name")
            or ""
        ).lower()
    )

    return banks


def validate_south_african_account(
    *,
    bank_code,
    account_number,
    account_name,
    account_type,
    document_type,
    document_number,
):

    if account_type not in {
        "personal",
        "business",
    }:

        raise PaystackError(
            "Invalid bank account type."
        )

    if document_type not in {
        "identityNumber",
        "passportNumber",
        "businessRegistrationNumber",
    }:

        raise PaystackError(
            "Invalid identity document type."
        )

    data = {
        "bank_code": bank_code,
        "country_code": "ZA",
        "account_number": account_number,
        "account_name": account_name,
        "account_type": account_type,
        "document_type": document_type,
        "document_number": document_number,
    }

    payload = _request(
        "POST",
        "/bank/validate",
        json_data=data,
    )

    return (
        payload.get("data")
        or {}
    )


def create_creator_subaccount(
    *,
    business_name,
    bank_code,
    account_number,
    creator_email=None,
    creator_name=None,
):

    data = {
        "business_name": business_name,
        "settlement_bank": bank_code,
        "account_number": account_number,

        # Paystack defines percentage_charge as
        # the percentage received by the main
        # Paystack account.
        #
        # Kalxa takes 0% platform commission.
        "percentage_charge": 0,

        "description": (
            "Creator payout account for "
            f"{business_name}"
        ),
    }

    if creator_email:

        data[
            "primary_contact_email"
        ] = creator_email

    if creator_name:

        data[
            "primary_contact_name"
        ] = creator_name

    payload = _request(
        "POST",
        "/subaccount",
        json_data=data,
    )

    return payload["data"]
