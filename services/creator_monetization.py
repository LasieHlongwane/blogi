"""Server-side plan gating and immutable per-transaction Kalxa fees."""
from decimal import Decimal, ROUND_HALF_UP


FEATURES = {
    'free': frozenset({'buy_me_coffee'}),
    'standard': frozenset({'buy_me_coffee', 'donations', 'exclusive_content'}),
    'premium': frozenset({'buy_me_coffee', 'donations', 'exclusive_content',
                          'fundraising', 'custom_domain'}),
}


def paid_plan_active(creator):
    return (creator.account_status == 'active'
            and creator.plan in ('standard', 'premium')
            and creator.payment_status == 'paid'
            and creator.registration_paid_at is not None)


def can_use_feature(creator, feature):
    if not creator or creator.account_status != 'active':
        return False
    if creator.plan == 'free':
        return feature in FEATURES['free']
    return paid_plan_active(creator) and feature in FEATURES.get(creator.plan, ())


def commission_percent(creator):
    if not can_use_feature(creator, 'buy_me_coffee'):
        raise ValueError('Creator is not eligible to accept support')
    return 23 if creator.plan == 'free' else 3


def calculate_commission_cents(creator, amount_cents):
    if type(amount_cents) is not int or amount_cents <= 0:
        raise ValueError('Amount must be a positive integer number of cents')
    percent = commission_percent(creator)
    fee = int((Decimal(amount_cents) * Decimal(percent) / Decimal(100))
              .quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return fee


def create_pending_coffee_payment(*, creator, amount_cents, supporter_email=None):
    """Build ledger entry; caller must persist before provider initialization.

    IMPORTANT: this does not initialize a Paystack transaction or arrange
    splits. The actual payout split MUST be validated against Paystack's
    supported SA settlement configuration and verified by webhook.
    """
    from models import FanPayment
    fee = calculate_commission_cents(creator, amount_cents)
    return FanPayment(creator_account_id=creator.id, payment_type='support',
                      amount_cents=amount_cents, platform_fee_cents=fee,
                      currency='ZAR', provider='paystack', status='pending',
                      supporter_email=supporter_email)
