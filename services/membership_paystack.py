"""Paystack membership transactions, using the existing verified API client."""
import json
import re
from urllib.parse import urlsplit, quote
from services.paystack_service import PaystackError, _request, _response_data

REFERENCE_RE = re.compile(r'KALXA-MEM-[A-F0-9]{32}\Z')


def initialize_membership_payment(*, email, amount_cents, reference,
                                  subaccount_code, platform_fee_cents,
                                  callback_url, metadata):
    if not REFERENCE_RE.fullmatch(reference):
        raise PaystackError('Invalid membership reference')
    if type(amount_cents) is not int or not 3000 <= amount_cents <= 10_000_000:
        raise PaystackError('Invalid membership amount')
    if type(platform_fee_cents) is not int or not 0 < platform_fee_cents < amount_cents:
        raise PaystackError('Invalid membership commission')
    if not subaccount_code or not email or not isinstance(metadata, dict):
        raise PaystackError('Missing membership checkout data')
    if metadata.get('product_type') != 'creator_membership':
        raise PaystackError('Incorrect product type')
    if metadata.get('platform_fee_cents') != platform_fee_cents:
        raise PaystackError('Incorrect fee metadata')
    if metadata.get('creator_receivable_cents') != amount_cents - platform_fee_cents:
        raise PaystackError('Incorrect creator share')
    parsed = urlsplit(callback_url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise PaystackError('HTTPS callback required')
    payload = _request('POST', '/transaction/initialize', json_data={
        'email': email,
        'amount': str(amount_cents),
        'currency': 'ZAR',
        'reference': reference,
        'callback_url': callback_url,
        'subaccount': subaccount_code,
        'transaction_charge': platform_fee_cents,
        'bearer': 'subaccount',
        'metadata': json.dumps(metadata, separators=(',', ':')),
    })
    checkout = _response_data(payload)
    url = checkout.get('authorization_url')
    parsed = urlsplit(url) if isinstance(url, str) else None
    if (not parsed or parsed.scheme != 'https' or parsed.hostname != 'checkout.paystack.com'
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or checkout.get('reference') != reference):
        raise PaystackError('Invalid Paystack checkout response')
    return url


def verify_membership_transaction(reference):
    if not isinstance(reference, str) or not REFERENCE_RE.fullmatch(reference):
        raise PaystackError('Invalid membership reference')
    payload = _request('GET', '/transaction/verify/' + quote(reference, safe=''))
    data = _response_data(payload)
    if data.get('reference') != reference:
        raise PaystackError('Reference mismatch')
    return data
