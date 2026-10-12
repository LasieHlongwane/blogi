"""Yoco checkout creation for one-time Kalxa activation and upgrades."""
import uuid
from urllib.parse import urlparse
import requests
from flask import current_app


class YocoError(Exception):
    pass


def get_yoco_secret_key():
    key = current_app.config.get('YOCO_SECRET_KEY')
    if not key:
        raise YocoError('Yoco payments are not configured.')
    return key


def get_yoco_checkout_url():
    return current_app.config.get('YOCO_CHECKOUT_URL', 'https://payments.yoco.com/api/checkouts')


def generate_checkout_reference():
    return 'creator_' + uuid.uuid4().hex


def create_checkout(*, amount_cents, creator, plan, success_url, cancel_url, failure_url):
    # Only the platform payments route decides the amount. This helper
    # verifies the amount is plausible; it cannot authorize a discount.
    if type(amount_cents) is not int or amount_cents not in (5000, 10000, 15000):
        raise YocoError('Invalid activation amount.')
    if plan not in ('standard', 'premium'):
        raise YocoError('Invalid activation plan.')
    if amount_cents == 5000 and plan != 'premium':
        raise YocoError('Invalid upgrade amount.')
    for target in (success_url, cancel_url, failure_url):
        parsed = urlparse(target)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
            raise YocoError('A secure return URL is required.')
    reference = generate_checkout_reference()
    payload = {
        'amount': amount_cents,
        'currency': 'ZAR',
        'successUrl': success_url,
        'cancelUrl': cancel_url,
        'failureUrl': failure_url,
        'clientReferenceId': reference,
        'externalId': reference,
        'metadata': {
            'creatorAccountId': str(creator.id),
            'creatorUsername': str(creator.username),
            'plan': plan,
            'checkoutReference': reference,
        },
    }
    headers = {
        'Authorization': f'Bearer {get_yoco_secret_key()}',
        'Content-Type': 'application/json',
        'Idempotency-Key': reference,
    }
    try:
        response = requests.post(get_yoco_checkout_url(), json=payload,
                                 headers=headers, timeout=30)
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        current_app.logger.exception('Yoco checkout communication failed')
        raise YocoError('Yoco checkout is temporarily unavailable.') from exc
    if not response.ok or not isinstance(data, dict):
        current_app.logger.error('Yoco checkout failed: HTTP %s', response.status_code)
        raise YocoError('Yoco could not create a checkout.')
    checkout_id, redirect_url = data.get('id'), data.get('redirectUrl')
    if not isinstance(checkout_id, str) or not checkout_id.strip():
        raise YocoError('Yoco returned no checkout ID.')
    if not isinstance(redirect_url, str) or urlparse(redirect_url).scheme != 'https':
        raise YocoError('Yoco returned no secure checkout URL.')
    return {
        'id': checkout_id.strip(), 'redirect_url': redirect_url,
        'status': data.get('status'), 'amount': data.get('amount'),
        'currency': data.get('currency'), 'processing_mode': data.get('processingMode'),
        'checkout_reference': reference, 'raw': data,
    }
