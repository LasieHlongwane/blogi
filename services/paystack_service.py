"""
Paystack integration for Kalxa Creator (ZAR).

Features:
- South African bank discovery
- Bank account validation
- Creator payout subaccounts
- Fan contribution checkout
- Immutable Kalxa commission
- Paystack transaction verification
- Secure webhook signature verification

Commission:
    Free:      23%
    Standard:   3%
    Premium:    3%

IMPORTANT:
This service does not calculate commission percentages.

The calling route calculates and stores the commission
before creating a Paystack transaction.

The stored commission must remain unchanged after a
creator upgrades or changes subscription plans.
"""

import hashlib
import hmac
import json
import os
import re

from urllib.parse import (
    quote,
    urlparse,
)

import requests


# ============================================================
# CONFIGURATION
# ============================================================

PAYSTACK_BASE_URL = "https://api.paystack.co"

TIMEOUT_SECONDS = 20

MAX_PAYMENT_CENTS = 10_000_000

PAYMENT_CURRENCY = "ZAR"

PAYSTACK_CHECKOUT_HOSTS = {
    "checkout.paystack.com",
}

FAN_REFERENCE_PATTERN = re.compile(
    r"^KALXA-FAN-[A-F0-9]{32}$"
)


# ============================================================
# EXCEPTIONS
# ============================================================

class PaystackError(Exception):
    """
    Raised when Paystack configuration, communication,
    or response validation fails.
    """


# ============================================================
# SECRET KEY
# ============================================================

def get_paystack_secret_key():

    key = (
        os.getenv(
            "PAYSTACK_SECRET_KEY",
            "",
        )
        .strip()
    )

    if not key:

        raise PaystackError(
            "PAYSTACK_SECRET_KEY is not configured."
        )

    if not key.startswith(
        ("sk_test_", "sk_live_")
    ):

        raise PaystackError(
            "Invalid Paystack secret key format."
        )

    return key


# ============================================================
# REQUEST HEADERS
# ============================================================

def _headers():

    return {
        "Authorization": (
            f"Bearer {get_paystack_secret_key()}"
        ),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ============================================================
# PAYSTACK API REQUEST
# ============================================================

def _request(
    method,
    path,
    *,
    json_data=None,
    params=None,
):
    """
    Make an authenticated request to Paystack.

    The returned object is the outer Paystack API response.

    Example:

    {
        "status": true,
        "message": "...",
        "data": {...}
    }
    """

    if method not in {
        "GET",
        "POST",
        "PUT",
        "DELETE",
    }:

        raise PaystackError(
            "Unsupported Paystack request method."
        )

    if not isinstance(path, str):

        raise PaystackError(
            "Invalid Paystack API path."
        )

    if not path.startswith("/"):

        raise PaystackError(
            "Invalid Paystack API path."
        )

    try:

        response = requests.request(
            method,
            f"{PAYSTACK_BASE_URL}{path}",
            headers=_headers(),
            json=json_data,
            params=params,
            timeout=TIMEOUT_SECONDS,
            allow_redirects=False,
        )

    except requests.Timeout as exc:

        raise PaystackError(
            "Paystack request timed out."
        ) from exc

    except requests.RequestException as exc:

        raise PaystackError(
            "Could not connect to Paystack."
        ) from exc

    # --------------------------------------------------------
    # HTTP STATUS
    # --------------------------------------------------------

    if not response.ok:

        raise PaystackError(
            (
                "Paystack API request failed. "
                f"HTTP status: {response.status_code}"
            )
        )

    # --------------------------------------------------------
    # JSON RESPONSE
    # --------------------------------------------------------

    try:

        payload = response.json()

    except ValueError as exc:

        raise PaystackError(
            "Paystack returned an invalid JSON response."
        ) from exc

    if not isinstance(payload, dict):

        raise PaystackError(
            "Paystack returned an unexpected response."
        )

    # --------------------------------------------------------
    # PAYSTACK APPLICATION STATUS
    # --------------------------------------------------------

    if payload.get("status") is not True:

        raise PaystackError(
            "Paystack rejected the API request."
        )

    return payload


# ============================================================
# RESPONSE DATA
# ============================================================

def _response_data(payload):

    if not isinstance(payload, dict):

        raise PaystackError(
            "Invalid Paystack response."
        )

    data = payload.get(
        "data"
    )

    if not isinstance(data, dict):

        raise PaystackError(
            "Paystack response is missing transaction data."
        )

    return data


# ============================================================
# AMOUNT VALIDATION
# ============================================================

def _positive_cents(
    value,
    field_name,
):

    if type(value) is not int:

        raise PaystackError(
            f"Invalid {field_name}."
        )

    if not (
        1 <= value <= MAX_PAYMENT_CENTS
    ):

        raise PaystackError(
            f"Invalid {field_name}."
        )

    return value


# ============================================================
# SECURE URL VALIDATION
# ============================================================

def _valid_https_url(value):

    if not isinstance(value, str):

        return False

    try:

        parsed = urlparse(
            value
        )

    except ValueError:

        return False

    if parsed.scheme != "https":

        return False

    if not parsed.hostname:

        return False

    if parsed.username or parsed.password:

        return False

    return True


def _valid_paystack_checkout_url(value):

    if not _valid_https_url(value):

        return False

    try:

        parsed = urlparse(
            value
        )

    except ValueError:

        return False

    if parsed.hostname not in PAYSTACK_CHECKOUT_HOSTS:

        return False

    if parsed.port not in {
        None,
        443,
    }:

        return False

    return True


# ============================================================
# SOUTH AFRICAN BANKS
# ============================================================

def list_south_african_banks(
    verification_only=True,
):
    """
    Retrieve South African banks supported by Paystack.
    """

    params = {
        "currency": PAYMENT_CURRENCY,
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

    banks = payload.get(
        "data"
    )

    if not isinstance(banks, list):

        raise PaystackError(
            "Paystack returned an invalid bank list."
        )

    return sorted(
        banks,
        key=lambda bank: str(
            bank.get("name")
            or ""
        ).lower(),
    )


# ============================================================
# SOUTH AFRICAN BANK ACCOUNT VALIDATION
# ============================================================

def validate_south_african_account(
    *,
    bank_code,
    account_number,
    account_name,
    account_type,
    document_type,
    document_number,
):
    """
    Validate South African bank account details.
    """

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

    required_fields = (
        bank_code,
        account_number,
        account_name,
        document_number,
    )

    for field in required_fields:

        if not isinstance(field, str):

            raise PaystackError(
                "Missing bank verification information."
            )

        if not field.strip():

            raise PaystackError(
                "Missing bank verification information."
            )

    payload = _request(
        "POST",
        "/bank/validate",
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

    return _response_data(
        payload
    )


# ============================================================
# CREATOR PAYOUT SUBACCOUNTS
# ============================================================

def create_creator_subaccount(
    *,
    business_name,
    bank_code,
    account_number,
    creator_email=None,
    creator_name=None,
):
    """
    Create a Paystack subaccount for a creator.

    IMPORTANT:

    percentage_charge=0 is the default.

    Every fan transaction must supply transaction_charge
    to apply Kalxa's immutable commission.
    """

    required_fields = (
        business_name,
        bank_code,
        account_number,
    )

    if not all(
        isinstance(value, str)
        and value.strip()
        for value in required_fields
    ):

        raise PaystackError(
            "Missing creator payout account details."
        )

    data = {
        "business_name": business_name.strip(),

        "settlement_bank": bank_code.strip(),

        "account_number": account_number.strip(),

        "percentage_charge": 0,

        "description": (
            "Creator payout account for "
            f"{business_name.strip()}"
        ),
    }

    if creator_email:

        data[
            "primary_contact_email"
        ] = creator_email.strip()

    if creator_name:

        data[
            "primary_contact_name"
        ] = creator_name.strip()

    payload = _request(
        "POST",
        "/subaccount",
        json_data=data,
    )

    return _response_data(
        payload
    )


# ============================================================
# FETCH CREATOR SUBACCOUNT
# ============================================================

def fetch_subaccount(
    subaccount_code,
):

    if not isinstance(
        subaccount_code,
        str,
    ):

        raise PaystackError(
            "Subaccount code is required."
        )

    subaccount_code = (
        subaccount_code.strip()
    )

    if not subaccount_code:

        raise PaystackError(
            "Subaccount code is required."
        )

    encoded_code = quote(
        subaccount_code,
        safe="",
    )

    payload = _request(
        "GET",
        f"/subaccount/{encoded_code}",
    )

    return _response_data(
        payload
    )


# ============================================================
# FAN PAYMENT INITIALIZATION
# ============================================================

def initialize_fan_payment(
    *,
    email,
    amount_cents,
    reference,
    subaccount_code,
    platform_fee_cents,
    callback_url,
    metadata,
):
    """
    Initialize a Paystack transaction.

    The creator receives the contribution less Kalxa's
    immutable platform commission, before processing fees.

    transaction_charge is supplied for each payment.

    bearer=subaccount requests that the creator bears
    Paystack processing fees.

    The exact provider settlement must be checked against
    Paystack's settlement records.
    """

    # --------------------------------------------------------
    # AMOUNT
    # --------------------------------------------------------

    amount_cents = _positive_cents(
        amount_cents,
        "payment amount",
    )

    # --------------------------------------------------------
    # COMMISSION
    # --------------------------------------------------------

    if type(platform_fee_cents) is not int:

        raise PaystackError(
            "Platform commission must be integer cents."
        )

    if not (
        0 < platform_fee_cents < amount_cents
    ):

        raise PaystackError(
            "Platform commission must be positive and less than amount."
        )

    # --------------------------------------------------------
    # EMAIL
    # --------------------------------------------------------

    if not isinstance(email, str):

        raise PaystackError(
            "Supporter email is required."
        )

    email = email.strip()

    if not email:

        raise PaystackError(
            "Supporter email is required."
        )

    # --------------------------------------------------------
    # REFERENCE
    # --------------------------------------------------------

    if not isinstance(reference, str):

        raise PaystackError(
            "Payment reference is required."
        )

    reference = reference.strip()

    if not FAN_REFERENCE_PATTERN.fullmatch(
        reference
    ):

        raise PaystackError(
            "Invalid fan payment reference."
        )

    # --------------------------------------------------------
    # SUBACCOUNT
    # --------------------------------------------------------

    if not isinstance(
        subaccount_code,
        str,
    ):

        raise PaystackError(
            "Creator payout account is not connected."
        )

    subaccount_code = (
        subaccount_code.strip()
    )

    if not subaccount_code:

        raise PaystackError(
            "Creator payout account is not connected."
        )

    # --------------------------------------------------------
    # CALLBACK URL
    # --------------------------------------------------------

    if not _valid_https_url(
        callback_url
    ):

        raise PaystackError(
            "A secure HTTPS callback URL is required."
        )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    if not isinstance(metadata, dict):

        raise PaystackError(
            "Payment metadata must be an object."
        )

    if (
        metadata.get("platform_fee_cents")
        != platform_fee_cents
    ):

        raise PaystackError(
            "Commission metadata mismatch."
        )

    expected_creator_receivable = (
        amount_cents
        - platform_fee_cents
    )

    if (
        metadata.get("creator_receivable_cents")
        != expected_creator_receivable
    ):

        raise PaystackError(
            "Creator share metadata mismatch."
        )

    if metadata.get(
        "fan_payment_id"
    ) is None:

        raise PaystackError(
            "Fan payment metadata is missing."
        )

    if metadata.get(
        "creator_account_id"
    ) is None:

        raise PaystackError(
            "Creator metadata is missing."
        )

    if metadata.get(
        "payment_type"
    ) not in {
        "support",
        "campaign",
    }:

        raise PaystackError(
            "Invalid payment type metadata."
        )

    # --------------------------------------------------------
    # PAYSTACK REQUEST
    # --------------------------------------------------------

    data = {
        "email": email,

        "amount": str(
            amount_cents
        ),

        "currency": PAYMENT_CURRENCY,

        "reference": reference,

        "callback_url": callback_url,

        "subaccount": subaccount_code,

        "transaction_charge": (
            platform_fee_cents
        ),

        "bearer": "subaccount",

        "metadata": json.dumps(
            metadata,
            separators=(",", ":"),
        ),
    }

    # --------------------------------------------------------
    # INITIALIZE
    # --------------------------------------------------------

    payload = _request(
        "POST",
        "/transaction/initialize",
        json_data=data,
    )

    checkout = _response_data(
        payload
    )

    # --------------------------------------------------------
    # VALIDATE CHECKOUT RESPONSE
    # --------------------------------------------------------

    authorization_url = (
        checkout.get(
            "authorization_url"
        )
    )

    provider_reference = (
        checkout.get(
            "reference"
        )
    )

    if not _valid_paystack_checkout_url(
        authorization_url
    ):

        raise PaystackError(
            "Paystack did not return a valid checkout URL."
        )

    if provider_reference != reference:

        raise PaystackError(
            "Paystack returned a different payment reference."
        )

    return checkout


# ============================================================
# VERIFY PAYSTACK TRANSACTION
# ============================================================

def verify_transaction(reference):
    """
    Verify a transaction directly with Paystack.

    IMPORTANT:

    This returns the transaction data dictionary.

    Example:

    {
        "id": 12345,
        "status": "success",
        "reference": "KALXA-FAN-...",
        "amount": 2000,
        "currency": "ZAR",
        "metadata": {...}
    }

    The calling route must validate the returned data
    against its own stored FanPayment record.
    """

    if not isinstance(reference, str):

        raise PaystackError(
            "Payment reference is required."
        )

    reference = reference.strip()

    if not FAN_REFERENCE_PATTERN.fullmatch(
        reference
    ):

        raise PaystackError(
            "Invalid fan payment reference."
        )

    encoded_reference = quote(
        reference,
        safe="",
    )

    payload = _request(
        "GET",
        (
            "/transaction/verify/"
            f"{encoded_reference}"
        ),
    )

    verified_data = _response_data(
        payload
    )

    # --------------------------------------------------------
    # BASIC PROVIDER RESPONSE VALIDATION
    # --------------------------------------------------------

    provider_reference = (
        verified_data.get(
            "reference"
        )
    )

    if provider_reference != reference:

        raise PaystackError(
            "Paystack transaction reference mismatch."
        )

    return verified_data


# ============================================================
# VERIFY PAYSTACK WEBHOOK SIGNATURE
# ============================================================

def verify_paystack_webhook(
    raw_body,
    signature,
):
    """
    Verify Paystack's HMAC-SHA512 webhook signature.

    Uses the exact raw request body and Paystack secret key.

    Returns True only when the signature matches.
    """

    if not isinstance(
        raw_body,
        bytes,
    ):

        return False

    if not isinstance(
        signature,
        str,
    ):

        return False

    signature = (
        signature.strip().lower()
    )

    if not signature:

        return False

    if not re.fullmatch(
        r"[a-f0-9]{128}",
        signature,
    ):

        return False

    expected = hmac.new(
        get_paystack_secret_key().encode(
            "utf-8"
        ),
        raw_body,
        hashlib.sha512,
    ).hexdigest()

    return hmac.compare_digest(
        expected,
        signature,
    )
