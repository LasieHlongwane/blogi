from datetime import datetime, timezone

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

from extensions import db


# ============================================================
# HELPERS
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    )


# ============================================================
# PLATFORM ADMIN
# ============================================================
#
# This remains your platform-level administrator.
#
# Creator users will NOT use this table.
# ============================================================

class AdminUser(db.Model):

    __tablename__ = "admin_users"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
        index=True,
    )

    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False,
    )

    last_login_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    def set_password(
        self,
        password,
    ):

        self.password_hash = (
            generate_password_hash(
                password
            )
        )

    def check_password(
        self,
        password,
    ):

        return check_password_hash(
            self.password_hash,
            password,
        )


# ============================================================
# CREATOR ACCOUNT
# ============================================================
#
# SaaS tenant/account.
#
# account_status:
#
# pending_payment
# pending_approval
# active
# suspended
# rejected
#
# payment_status:
#
# unpaid
# paid
#
# subscription_status:
#
# inactive
# active
# past_due
# expired
# cancelled
#
# ============================================================

class CreatorAccount(db.Model):

    __tablename__ = "creator_accounts"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
        index=True,
    )

    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )

    # ========================================================
    # CREATOR PLAN
    # ========================================================

    plan = db.Column(
        db.String(30),
        default="standard",
        nullable=False,
        index=True,
    )

    # ========================================================
    # ACCOUNT APPROVAL
    # ========================================================

    account_status = db.Column(
        db.String(30),
        default="pending_payment",
        nullable=False,
        index=True,
    )

    # ========================================================
    # INITIAL PLATFORM PAYMENT
    # ========================================================

    payment_status = db.Column(
        db.String(30),
        default="unpaid",
        nullable=False,
        index=True,
    )

    registration_paid_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    # ========================================================
    # PLATFORM APPROVAL
    # ========================================================

    approved_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    # ========================================================
    # LEGACY MONTHLY SAAS SUBSCRIPTION FIELDS
    # ========================================================

    subscription_status = db.Column(
        db.String(30),
        default="inactive",
        nullable=False,
        index=True,
    )

    subscription_started_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    subscription_expires_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # ========================================================
    # LOGIN
    # ========================================================

    last_login_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    # ========================================================
    # TIMESTAMPS
    # ========================================================

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # ========================================================
    # PASSWORD
    # ========================================================

    def set_password(
        self,
        password,
    ):

        self.password_hash = (
            generate_password_hash(
                password
            )
        )

    def check_password(
        self,
        password,
    ):

        return check_password_hash(
            self.password_hash,
            password,
        )


# ============================================================
# PLATFORM SUBSCRIPTION
# ============================================================

class PlatformSubscription(db.Model):

    __tablename__ = "platform_subscriptions"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    creator_account_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "creator_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    plan = db.Column(
        db.String(30),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="inactive",
        index=True,
    )

    provider = db.Column(
        db.String(30),
        nullable=True,
        index=True,
    )

    provider_subscription_id = db.Column(
        db.String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    started_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    current_period_start = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    current_period_end = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    grace_period_ends_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    cancelled_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    creator_account = db.relationship(
        "CreatorAccount",
        backref=db.backref(
            "platform_subscription",
            uselist=False,
            cascade="all, delete-orphan",
            single_parent=True,
        ),
    )


# ============================================================
# PLATFORM SUBSCRIPTION PAYMENT
# ============================================================
#
# Creator -> platform payment history.
#
# This is separate from FanPayment.
#
# PlatformSubscriptionPayment:
#     creator pays Kalxa.
#
# FanPayment:
#     fan/supporter pays creator.
#
# ============================================================

class PlatformSubscriptionPayment(db.Model):

    __tablename__ = (
        "platform_subscription_payments"
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    creator_account_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "creator_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    subscription_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "platform_subscriptions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    plan = db.Column(
        db.String(30),
        nullable=False,
        index=True,
    )

    amount_cents = db.Column(
        db.Integer,
        nullable=False,
    )

    currency = db.Column(
        db.String(10),
        nullable=False,
        default="ZAR",
    )

    provider = db.Column(
        db.String(30),
        nullable=False,
        default="yoco",
        index=True,
    )

    provider_reference = db.Column(
        db.String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    # pending / paid / failed / refunded

    status = db.Column(
        db.String(30),
        nullable=False,
        default="pending",
        index=True,
    )

    paid_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    creator_account = db.relationship(
        "CreatorAccount",
        backref=db.backref(
            "platform_subscription_payments",
            lazy=True,
        ),
    )

    subscription = db.relationship(
        "PlatformSubscription",
        backref=db.backref(
            "payments",
            lazy=True,
        ),
    )


# ============================================================
# CREATOR PAYOUT ACCOUNT
# ============================================================
#
# Creator's external payout connection.
#
# Available to:
#
# Standard
# Premium
#
# Provider initially:
#
# paystack
#
# One creator has at most one current payout account.
#
# IMPORTANT:
#
# Do not store creator banking credentials or sensitive
# authentication information here.
#
# The provider subaccount code is the important identifier
# used when creating fan payments.
#
# status:
#
# pending
# active
# disabled
# ============================================================

class CreatorPayoutAccount(db.Model):

    __tablename__ = "creator_payout_accounts"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    creator_account_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "creator_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    provider = db.Column(
        db.String(30),
        nullable=False,
        default="paystack",
        index=True,
    )

    provider_subaccount_code = db.Column(
        db.String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    # ========================================================
    # PAYOUT DISPLAY / AUDIT INFORMATION
    # ========================================================

    business_name = db.Column(
        db.String(180),
        nullable=True,
    )

    account_name = db.Column(
        db.String(180),
        nullable=True,
    )

    settlement_bank = db.Column(
        db.String(180),
        nullable=True,
    )

    # Only the final four digits should be retained here
    # after payout onboarding.

    account_number_last4 = db.Column(
        db.String(4),
        nullable=True,
    )

    # ========================================================
    # PROVIDER CHARGE CONFIGURATION
    # ========================================================
    #
    # Keep this for provider configuration/audit.
    #
    # Kalxa's platform commission on voluntary support can
    # remain 0 even though payment processing fees may apply.
    # ========================================================

    percentage_charge = db.Column(
        db.Numeric(
            5,
            2,
        ),
        nullable=False,
        default=0,
    )

    # pending / active / disabled

    status = db.Column(
        db.String(30),
        nullable=False,
        default="pending",
        index=True,
    )

    connected_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    disabled_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    creator_account = db.relationship(
        "CreatorAccount",
        backref=db.backref(
            "payout_account",
            uselist=False,
            cascade="all, delete-orphan",
            single_parent=True,
        ),
    )


# ============================================================
# CREATOR PROFILE
# ============================================================

class CreatorProfile(db.Model):

    __tablename__ = "creator_profiles"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    creator_account_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "creator_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        unique=True,
        index=True,
    )

    # ========================================================
    # BASIC PROFILE
    # ========================================================

    display_name = db.Column(
        db.String(120),
        nullable=False,
    )

    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
        index=True,
    )

    tagline = db.Column(
        db.String(255),
        nullable=True,
    )

    bio = db.Column(
        db.Text,
        nullable=True,
    )

    # ========================================================
    # PROFILE IMAGE
    # ========================================================

    profile_image_url = db.Column(
        db.Text,
        nullable=True,
    )

    profile_image_public_id = db.Column(
        db.String(500),
        nullable=True,
    )

    # ========================================================
    # INTRO REEL
    # ========================================================

    intro_reel_url = db.Column(
        db.Text,
        nullable=True,
    )

    intro_reel_public_id = db.Column(
        db.String(500),
        nullable=True,
    )

    intro_reel_thumbnail_url = db.Column(
        db.Text,
        nullable=True,
    )

    # ========================================================
    # SOCIAL LINKS
    # ========================================================

    instagram_url = db.Column(
        db.Text,
        nullable=True,
    )

    tiktok_url = db.Column(
        db.Text,
        nullable=True,
    )

    youtube_url = db.Column(
        db.Text,
        nullable=True,
    )

    # ========================================================
    # TIMESTAMPS
    # ========================================================

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    creator_account = db.relationship(
        "CreatorAccount",
        backref=db.backref(
            "profile",
            uselist=False,
            cascade="all, delete-orphan",
            single_parent=True,
        ),
    )


# ============================================================
# CONTENT CATEGORY / FOLDER
# ============================================================

class ContentCategory(db.Model):

    __tablename__ = "content_categories"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    creator_account_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "creator_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    name = db.Column(
        db.String(100),
        nullable=False,
    )

    slug = db.Column(
        db.String(120),
        nullable=False,
        index=True,
    )

    description = db.Column(
        db.Text,
        nullable=True,
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False,
    )

    display_order = db.Column(
        db.Integer,
        default=0,
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    creator_account = db.relationship(
        "CreatorAccount",
        backref=db.backref(
            "categories",
            lazy=True,
        ),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "creator_account_id",
            "slug",
            name=(
                "uq_content_category_"
                "creator_slug"
            ),
        ),
    )


# ============================================================
# CONTENT POST
# ============================================================

class ContentPost(db.Model):

    __tablename__ = "content_posts"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    creator_account_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "creator_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    category_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "content_categories.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    title = db.Column(
        db.String(200),
        nullable=False,
    )

    slug = db.Column(
        db.String(220),
        nullable=False,
        index=True,
    )

    excerpt = db.Column(
        db.Text,
        nullable=True,
    )

    body = db.Column(
        db.Text,
        nullable=True,
    )

    cover_image_url = db.Column(
        db.Text,
        nullable=True,
    )

    # story / reel / vlog

    content_type = db.Column(
        db.String(30),
        nullable=False,
        default="story",
        index=True,
    )

    # public / subscriber

    access_level = db.Column(
        db.String(30),
        nullable=False,
        default="public",
        index=True,
    )

    # draft / published / archived

    status = db.Column(
        db.String(30),
        nullable=False,
        default="draft",
        index=True,
    )

    is_featured = db.Column(
        db.Boolean,
        default=False,
        nullable=False,
    )

    published_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    category = db.relationship(
        "ContentCategory",
        backref=db.backref(
            "posts",
            lazy=True,
        ),
    )

    creator_account = db.relationship(
        "CreatorAccount",
        backref=db.backref(
            "posts",
            lazy=True,
        ),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "creator_account_id",
            "slug",
            name=(
                "uq_content_post_"
                "creator_slug"
            ),
        ),
    )


# ============================================================
# CONTENT MEDIA
# ============================================================

class ContentMedia(db.Model):

    __tablename__ = "content_media"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    post_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "content_posts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # cover / gallery_image / video

    media_type = db.Column(
        db.String(20),
        nullable=False,
    )

    media_url = db.Column(
        db.Text,
        nullable=False,
    )

    public_id = db.Column(
        db.String(500),
        nullable=True,
        index=True,
    )

    resource_type = db.Column(
        db.String(30),
        nullable=True,
    )

    thumbnail_url = db.Column(
        db.Text,
        nullable=True,
    )

    caption = db.Column(
        db.String(255),
        nullable=True,
    )

    media_order = db.Column(
        db.Integer,
        default=0,
        nullable=False,
    )

    duration_seconds = db.Column(
        db.Float,
        nullable=True,
    )

    width = db.Column(
        db.Integer,
        nullable=True,
    )

    height = db.Column(
        db.Integer,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    post = db.relationship(
        "ContentPost",
        backref=db.backref(
            "media",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )


# ============================================================
# COMMENT
# ============================================================

class Comment(db.Model):

    __tablename__ = "comments"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    post_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "content_posts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    parent_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "comments.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    author_name = db.Column(
        db.String(80),
        nullable=False,
    )

    body = db.Column(
        db.Text,
        nullable=False,
    )

    # pending / approved / hidden

    status = db.Column(
        db.String(20),
        nullable=False,
        default="approved",
        index=True,
    )

    is_creator = db.Column(
        db.Boolean,
        default=False,
        nullable=False,
    )

    anonymous_session_id = db.Column(
        db.String(100),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    post = db.relationship(
        "ContentPost",
        backref=db.backref(
            "comments",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )

    replies = db.relationship(
        "Comment",
        backref=db.backref(
            "parent",
            remote_side=[id],
        ),
        lazy=True,
        cascade="all, delete-orphan",
        order_by="Comment.created_at.asc()",
    )


# ============================================================
# EMAIL SUBSCRIBER
# ============================================================

class EmailSubscriber(db.Model):

    __tablename__ = "email_subscribers"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    creator_account_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "creator_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    email = db.Column(
        db.String(255),
        nullable=False,
        index=True,
    )

    # pending / active / unsubscribed

    status = db.Column(
        db.String(30),
        default="pending",
        nullable=False,
        index=True,
    )

    verification_token = db.Column(
        db.String(255),
        unique=True,
        nullable=True,
        index=True,
    )

    unsubscribe_token = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    verified_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    unsubscribed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    creator_account = db.relationship(
        "CreatorAccount",
        backref=db.backref(
            "email_subscribers",
            lazy=True,
        ),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "creator_account_id",
            "email",
            name=(
                "uq_email_subscriber_"
                "creator_email"
            ),
        ),
    )


# ============================================================
# EMAIL DELIVERY
# ============================================================

class EmailDelivery(db.Model):

    __tablename__ = "email_deliveries"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    subscriber_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "email_subscribers.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    post_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "content_posts.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    # verification / welcome / new_post

    email_type = db.Column(
        db.String(50),
        nullable=False,
        index=True,
    )

    recipient_email = db.Column(
        db.String(255),
        nullable=False,
        index=True,
    )

    subject = db.Column(
        db.String(255),
        nullable=False,
    )

    # sent / failed

    status = db.Column(
        db.String(30),
        nullable=False,
        index=True,
    )

    error_message = db.Column(
        db.Text,
        nullable=True,
    )

    sent_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    subscriber = db.relationship(
        "EmailSubscriber",
        backref=db.backref(
            "deliveries",
            lazy=True,
        ),
    )

    post = db.relationship(
        "ContentPost",
        backref=db.backref(
            "email_deliveries",
            lazy=True,
        ),
    )


# ============================================================
# FUNDRAISING CAMPAIGN
# ============================================================
#
# Premium-only creator feature.
#
# This table stores the campaign definition.
#
# Financial truth does NOT live in an amount_raised column.
#
# Confirmed FanPayment records are the source of truth for
# campaign contributions.
#
# status:
#
# draft
# active
# completed
# cancelled
# archived
#
# ============================================================

class FundraisingCampaign(db.Model):

    __tablename__ = "fundraising_campaigns"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    creator_account_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "creator_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    title = db.Column(
        db.String(180),
        nullable=False,
    )

    slug = db.Column(
        db.String(200),
        nullable=False,
        index=True,
    )

    description = db.Column(
        db.Text,
        nullable=False,
    )

    # ========================================================
    # COVER IMAGE
    # ========================================================

    cover_image_url = db.Column(
        db.Text,
        nullable=True,
    )

    cover_image_public_id = db.Column(
        db.String(500),
        nullable=True,
    )

    # ========================================================
    # FUNDING GOAL
    # ========================================================
    #
    # Always store money in cents.
    #
    # R15,000 = 1,500,000 cents
    # ========================================================

    goal_amount_cents = db.Column(
        db.Integer,
        nullable=False,
    )

    currency = db.Column(
        db.String(10),
        nullable=False,
        default="ZAR",
    )

    # ========================================================
    # CAMPAIGN STATE
    # ========================================================

    status = db.Column(
        db.String(30),
        nullable=False,
        default="draft",
        index=True,
    )

    starts_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    ends_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    published_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    completed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    cancelled_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # ========================================================
    # RELATIONSHIP
    # ========================================================

    creator_account = db.relationship(
        "CreatorAccount",
        backref=db.backref(
            "fundraising_campaigns",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )

    # ========================================================
    # TENANT-SCOPED SLUG
    # ========================================================

    __table_args__ = (
        db.UniqueConstraint(
            "creator_account_id",
            "slug",
            name=(
                "uq_fundraising_campaign_"
                "creator_slug"
            ),
        ),
        db.CheckConstraint(
            "goal_amount_cents > 0",
            name=(
                "ck_fundraising_campaign_"
                "positive_goal"
            ),
        ),
    )



class CreatorBranding(db.Model):

    __tablename__ = "creator_brandings"

    id = db.Column(db.Integer, primary_key=True)

    creator_account_id = db.Column(
        db.Integer,
        db.ForeignKey("creator_accounts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    site_title = db.Column(db.String(180))
    site_tagline = db.Column(db.String(255))

    logo_url = db.Column(db.Text)
    logo_public_id = db.Column(db.String(500))

    favicon_url = db.Column(db.Text)
    favicon_public_id = db.Column(db.String(500))

    cover_image_url = db.Column(db.Text)
    cover_image_public_id = db.Column(db.String(500))

    primary_color = db.Column(
        db.String(20), nullable=False, default="#111318"
    )

    accent_color = db.Column(
        db.String(20), nullable=False, default="#d4a75d"
    )

    background_color = db.Column(
        db.String(20), nullable=False, default="#ffffff"
    )

    text_color = db.Column(
        db.String(20), nullable=False, default="#17191d"
    )

    theme = db.Column(
        db.String(40), nullable=False, default="default"
    )

    font_family = db.Column(
        db.String(80), nullable=False, default="system"
    )

    footer_text = db.Column(db.String(255))

    show_platform_branding = db.Column(
        db.Boolean, nullable=False, default=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    creator_account = db.relationship(
        "CreatorAccount",
        backref=db.backref(
            "branding",
            uselist=False,
            cascade="all, delete-orphan",
            single_parent=True,
        ),
    )


class CreatorDomain(db.Model):

    __tablename__ = "creator_domains"

    id = db.Column(db.Integer, primary_key=True)

    creator_account_id = db.Column(
        db.Integer,
        db.ForeignKey("creator_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    hostname = db.Column(
        db.String(253),
        nullable=False,
        unique=True,
        index=True,
    )

    # subdomain / custom
    domain_type = db.Column(
        db.String(30),
        nullable=False,
        default="subdomain",
        index=True,
    )

    # pending / verified / failed
    verification_status = db.Column(
        db.String(30),
        nullable=False,
        default="pending",
        index=True,
    )

    verification_token = db.Column(
        db.String(255),
        unique=True,
    )

    is_primary = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    verified_at = db.Column(db.DateTime(timezone=True))
    activated_at = db.Column(db.DateTime(timezone=True))

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    creator_account = db.relationship(
        "CreatorAccount",
        backref=db.backref(
            "domains",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )

    __table_args__ = (
        db.CheckConstraint(
            "domain_type IN ('subdomain', 'custom')",
            name="ck_creator_domain_type",
        ),
    )
# ============================================================
# FAN PAYMENT
# ============================================================
#
# Fan/supporter -> creator payment ledger.
#
# This is completely separate from creator -> platform
# subscription payments.
#
# payment_type:
#
# support
# campaign
# membership        (future)
#
# status:
#
# pending
# paid
# failed
# refunded
#
# Provider initially:
#
# paystack
#
# IMPORTANT:
#
# The provider webhook will become the authoritative source
# for changing a pending FanPayment to paid.
#
# Never mark a FanPayment paid from a browser success URL.
# ============================================================

class FanPayment(db.Model):

    __tablename__ = "fan_payments"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    creator_account_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "creator_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "fundraising_campaigns.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    # support / campaign / membership

    payment_type = db.Column(
        db.String(30),
        nullable=False,
        default="support",
        index=True,
    )

    # ========================================================
    # SUPPORTER DETAILS
    # ========================================================

    supporter_name = db.Column(
        db.String(120),
        nullable=True,
    )

    supporter_email = db.Column(
        db.String(255),
        nullable=True,
        index=True,
    )

    supporter_message = db.Column(
        db.String(500),
        nullable=True,
    )

    is_anonymous = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    # ========================================================
    # PAYMENT AMOUNT
    # ========================================================

    amount_cents = db.Column(
        db.Integer,
        nullable=False,
    )

    currency = db.Column(
        db.String(10),
        nullable=False,
        default="ZAR",
    )

    # ========================================================
    # PLATFORM FEE
    # ========================================================
    #
    # For the initial Buy Me a Coffee model this can remain 0.
    #
    # Provider/payment-processing fees are separate from
    # Kalxa's own platform commission.
    # ========================================================

    platform_fee_cents = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    # ========================================================
    # PROVIDER
    # ========================================================

    provider = db.Column(
        db.String(30),
        nullable=False,
        default="paystack",
        index=True,
    )

    # Our payment/checkout reference sent to Paystack.

    provider_reference = db.Column(
        db.String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    # Provider transaction ID after payment confirmation.

    provider_transaction_id = db.Column(
        db.String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    # pending / paid / failed / refunded

    status = db.Column(
        db.String(30),
        nullable=False,
        default="pending",
        index=True,
    )

    paid_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    failed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    refunded_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # ========================================================
    # RELATIONSHIPS
    # ========================================================

    creator_account = db.relationship(
        "CreatorAccount",
        backref=db.backref(
            "fan_payments",
            lazy=True,
        ),
    )

    campaign = db.relationship(
        "FundraisingCampaign",
        backref=db.backref(
            "payments",
            lazy=True,
        ),
    )

    # ========================================================
    # DATABASE SAFETY
    # ========================================================

    __table_args__ = (
        db.CheckConstraint(
            "amount_cents > 0",
            name=(
                "ck_fan_payment_"
                "positive_amount"
            ),
        ),
        db.CheckConstraint(
            "platform_fee_cents >= 0",
            name=(
                "ck_fan_payment_"
                "nonnegative_platform_fee"
            ),
        ),
    )
