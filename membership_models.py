"""Creator-scoped membership records and single-use email login tokens."""
from datetime import datetime, timezone
from extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class MembershipSubscriber(db.Model):
    __tablename__ = 'membership_subscribers'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class CreatorMembership(db.Model):
    __tablename__ = 'creator_memberships'
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('membership_subscribers.id', ondelete='CASCADE'), nullable=False, index=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    monthly_amount_cents = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False, default='pending', index=True)
    current_period_start = db.Column(db.DateTime(timezone=True))
    current_period_end = db.Column(db.DateTime(timezone=True), index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    subscriber = db.relationship('MembershipSubscriber', backref=db.backref('memberships', lazy=True))
    creator_account = db.relationship('CreatorAccount', backref=db.backref('exclusive_memberships', lazy=True))
    __table_args__ = (
        db.UniqueConstraint('subscriber_id', 'creator_account_id', name='uq_membership_subscriber_creator'),
        db.CheckConstraint('monthly_amount_cents >= 3000', name='ck_membership_minimum_amount'),
    )


class MembershipPayment(db.Model):
    __tablename__ = 'membership_payments'
    id = db.Column(db.Integer, primary_key=True)
    membership_id = db.Column(db.Integer, db.ForeignKey('creator_memberships.id', ondelete='CASCADE'), nullable=False, index=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    platform_fee_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default='ZAR')
    provider = db.Column(db.String(30), nullable=False, default='paystack')
    provider_reference = db.Column(db.String(255), unique=True, nullable=False, index=True)
    provider_transaction_id = db.Column(db.String(255), unique=True)
    status = db.Column(db.String(30), nullable=False, default='pending', index=True)
    paid_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    membership = db.relationship('CreatorMembership', backref=db.backref('payments', lazy=True))
    __table_args__ = (
        db.CheckConstraint('amount_cents >= 3000', name='ck_membership_payment_minimum'),
        db.CheckConstraint('platform_fee_cents >= 0 AND platform_fee_cents < amount_cents', name='ck_membership_payment_fee'),
    )


class MembershipLoginToken(db.Model):
    __tablename__ = 'membership_login_tokens'
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('membership_subscribers.id', ondelete='CASCADE'), nullable=False, index=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    consumed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    __table_args__ = (
        db.Index('ix_membership_login_creator_subscriber_created', 'creator_account_id', 'subscriber_id', 'created_at'),
    )
