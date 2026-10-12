"""Paystack integration for Kalxa Creator (ZAR).

Fan contributions use a single creator subaccount and a per-transaction
flat override (`transaction_charge`) for Kalxa's immutable commission.
The calling route computes and stores the fee; this service never derives
fees from a mutable creator plan.
"""

import hashlib
import hmac
import json
import os
from urllib.parse import quote

import requests

PAYSTACK_BASE_URL = "https://api.paystack.co"
TIMEOUT_SECONDS = 20
MAX_PAYMENT_CENTS = 10_000_000


class PaystackError(Exception):
    """A Paystack request, validation, or configuration failed."""


def get_paystack_secret_key():
    key = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
    if not key:
        raise PaystackError("PAYSTACK_SECRET_KEY is not configured.")
    return key


def _headers():
    return {
        "Authorization": f"Bearer {get_paystack_secret_key()}",
        "Content-Type": "application/json",
    }


def _request(method, path, *, json_data=None, params=None):
    try:
        response = requests.request(
            method,
            f"{PAYSTACK_BASE_URL}{path}",
            headers=_headers(),
            json=json_data,
            params=params,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise PaystackError("Could not connect to Paystack.") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise PaystackError("Paystack returned an invalid JSON response.") from exc

    if not isinstance(payload, dict):
        raise PaystackError("Paystack returned an unexpected response.")

    if not response.ok or payload.get("status") is not True:
        # Do not include provider response in public error messages: it may
        # contain personally identifying banking information.
        raise PaystackError(
            f"Paystack request failed (HTTP {response.status_code})."
        )
    return payload


def _response_data(payload):
    data = payload.get("data")
    if not isinstance(data, dict):
        raise PaystackError("Paystack response is missing data.")
    return data


def _positive_cents(value, field_name):
    if type(value) is not int or not 1 <= value <= MAX_PAYMENT_CENTS:
        raise PaystackError(f"Invalid {field_name}.")
    return value


# ============================================================
# SOUTH AFRICAN BANKS AND ACCOUNT VALIDATION
# ============================================================

def list_south_african_banks(verification_only=True):
    params = {
        "currency": "ZAR",
        "country": "south africa",
        "perPage": 100,
    }
    if verification_only:
        params["enabled_for_verification"] = "true"

    payload = _request("GET", "/bank", params=params)
    banks = payload.get("data")
    if not isinstance(banks, list):
        raise PaystackError("Paystack returned an invalid bank list.")
    return sorted(
        banks,
        key=lambda bank: str(bank.get("name") or "").lower(),
    )


def validate_south_african_account(
    *, bank_code, account_number, account_name, account_type,
    document_type, document_number,
):
    if account_type not in {"personal", "business"}:
        raise PaystackError("Invalid bank account type.")
    if document_type not in {
        "identityNumber", "passportNumber", "businessRegistrationNumber"
    }:
        raise PaystackError("Invalid identity document type.")

    for field in (bank_code, account_number, account_name, document_number):
        if not isinstance(field, str) or not field.strip():
            raise PaystackError("Missing bank verification information.")

    payload = _request(
        "POST", "/bank/validate",
        json_data={
            "bank_code": bank_code.strip(),
            "country_code": "ZA",
            "account_number": account_number.strip(),
            "account_name": account_name.strip(),
            "account_type": account_type,
            "document_type": document_type,
            "document_number": document_number.strip(),
        },
    )
    return _response_data(payload)


# ============================================================
# CREATOR PAYOUT SUBACCOUNTS
# ============================================================

def create_creator_subaccount(
    *, business_name, bank_code, account_number,
    creator_email=None, creator_name=None,
):
    if not all(isinstance(x, str) and x.strip() for x in (
        business_name, bank_code, account_number
    )):
        raise PaystackError("Missing creator payout account details.")

    # The 0% default is intentional: EVERY new fan transaction supplies
    # transaction_charge, which overrides the subaccount's default split.
    # Do not use the subaccount's percentage_charge to implement 23%/3%,
    # since creators may upgrade and historical payments must remain fixed.
    data = {
        "business_name": business_name.strip(),
        "settlement_bank": bank_code.strip(),
        "account_number": account_number.strip(),
        "percentage_charge": 0,
        "description": f"Creator payout account for {business_name.strip()}",
    }
    if creator_email:
        data["primary_contact_email"] = creator_email.strip()
    if creator_name:
        data["primary_contact_name"] = creator_name.strip()

    return _response_data(_request("POST", "/subaccount", json_data=data))


def fetch_subaccount(subaccount_code):
    if not isinstance(subaccount_code, str) or not subaccount_code.strip():
        raise PaystackError("Subaccount code is required.")
    return _response_data(_request(
        "GET", f"/subaccount/{quote(subaccount_code.strip(), safe='')}"
    ))


# ============================================================
# FAN PAYMENT WITH EXACT PLATFORM COMMISSION
# ============================================================

def initialize_fan_payment(
    *, email, amount_cents, reference, subaccount_code,
    platform_fee_cents, callback_url, metadata,
):
    """Initialize a single-subaccount split with exact Kalxa fee in cents.

    `transaction_charge` overrides subaccount percentage for THIS payment.
    `bearer=subaccount` makes the creator bear Paystack processing fees;
    the creator's eventual net settlement may therefore be lower than
    `amount_cents - platform_fee_cents`.

    Fail closed when fee is missing or invalid: never silently charge 0%.
    """
    amount_cents = _positive_cents(amount_cents, "payment amount")

    if type(platform_fee_cents) is not int:
        raise PaystackError("Platform commission must be integer cents.")
    if not 0 < platform_fee_cents < amount_cents:
        raise PaystackError("Platform commission must be positive and less than amount.")

    if not isinstance(email, str) or not email.strip():
        raise PaystackError("Supporter email is required.")
    if not isinstance(reference, str) or not reference.strip():
        raise PaystackError("Payment reference is required.")
    if not isinstance(subaccount_code, str) or not subaccount_code.strip():
        raise PaystackError("Creator payout account is not connected.")
    if not isinstance(callback_url, str) or not callback_url.startswith("https://"):
        raise PaystackError("A secure HTTPS callback URL is required.")
    if not isinstance(metadata, dict):
        raise PaystackError("Payment metadata must be an object.")

    # Cross-check against immutable ledger values passed by the route.
    if metadata.get("platform_fee_cents") != platform_fee_cents:
        raise PaystackError("Commission metadata mismatch.")
    if metadata.get("creator_receivable_cents") != amount_cents - platform_fee_cents:
        raise PaystackError("Creator share metadata mismatch.")

    data = {
        "email": email.strip(),
        "amount": str(amount_cents),
        "currency": "ZAR",
        "reference": reference.strip(),
        "callback_url": callback_url,
        "subaccount": subaccount_code.strip(),
        "transaction_charge": platform_fee_cents,
        "bearer": "subaccount",
        "metadata": json.dumps(metadata, separators=(",", ":")),
    }

    checkout = _response_data(_request(
        "POST", "/transaction/initialize", json_data=data
    ))
    authorization_url = checkout.get("authorization_url")
    provider_reference = checkout.get("reference")
    if not isinstance(authorization_url, str) or not authorization_url.startswith("https://"):
        raise PaystackError("Paystack did not return a secure checkout URL.")
    if provider_reference != reference:
        raise PaystackError("Paystack returned a different payment reference.")
    return checkout


# ============================================================
# PAYMENT VERIFICATION AND WEBHOOK SIGNATURE
# ============================================================

def verify_transaction(reference):
    if not isinstance(reference, str) or not reference.strip():
        raise PaystackError("Payment reference is required.")
    return _response_data(_request(
        "GET", f"/transaction/verify/{quote(reference.strip(), safe='')}"
    ))


def verify_paystack_webhook(raw_body, signature):
    if not isinstance(raw_body, bytes) or not isinstance(signature, str):
        return False
    if not signature.strip():
        return False
    expected = hmac.new(
        get_paystack_secret_key().encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())
