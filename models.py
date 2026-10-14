from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class PasswordMixin:
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class AdminUser(PasswordMixin, db.Model):
    __tablename__ = 'admin_users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class CreatorAccount(PasswordMixin, db.Model):
    __tablename__ = "creator_accounts"

    id = db.Column(db.Integer, primary_key=True)

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

    # New creators start on Free.
    plan = db.Column(
        db.String(30),
        default="free",
        nullable=False,
        index=True,
    )

    account_status = db.Column(
        db.String(30),
        default="active",
        nullable=False,
        index=True,
    )

    payment_status = db.Column(
        db.String(30),
        default="unpaid",
        nullable=False,
        index=True,
    )

    registration_paid_at = db.Column(
        db.DateTime(timezone=True),
    )

    approved_at = db.Column(
        db.DateTime(timezone=True),
    )

    # Legacy subscription fields retained.
    subscription_status = db.Column(
        db.String(30),
        default="inactive",
        nullable=False,
        index=True,
    )

    subscription_started_at = db.Column(
        db.DateTime(timezone=True),
    )

    subscription_expires_at = db.Column(
        db.DateTime(timezone=True),
        index=True,
    )

    last_login_at = db.Column(
        db.DateTime(timezone=True),
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

    @property
    def monetization_enabled(self):
        """
        Free creators may receive Buy Me a Coffee support.

        Paid creators require a successful activation state.

        Other monetization restrictions must still be enforced
        by the relevant feature routes.
        """

        if self.account_status != "active":
            return False

        if self.plan == "free":
            return True

        if self.plan in ("standard", "premium"):
            return (
                self.payment_status == "paid"
                and self.registration_paid_at is not None
            )

        return False

class PlatformSubscription(db.Model):
    # Legacy subscription record retained to avoid breaking existing routes.
    __tablename__ = 'platform_subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    plan = db.Column(db.String(30), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default='inactive', index=True)
    provider = db.Column(db.String(30), index=True)
    provider_subscription_id = db.Column(db.String(255), unique=True, index=True)
    started_at = db.Column(db.DateTime(timezone=True))
    current_period_start = db.Column(db.DateTime(timezone=True))
    current_period_end = db.Column(db.DateTime(timezone=True), index=True)
    grace_period_ends_at = db.Column(db.DateTime(timezone=True), index=True)
    cancelled_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    creator_account = db.relationship('CreatorAccount', backref=db.backref('platform_subscription', uselist=False, cascade='all, delete-orphan', single_parent=True))


class PlatformSubscriptionPayment(db.Model):
    # Reused as the immutable-price one-time activation / upgrade ledger.
    __tablename__ = 'platform_subscription_payments'
    id = db.Column(db.Integer, primary_key=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('platform_subscriptions.id', ondelete='SET NULL'), index=True)
    plan = db.Column(db.String(30), nullable=False, index=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default='ZAR')
    provider = db.Column(db.String(30), nullable=False, default='yoco', index=True)
    provider_reference = db.Column(db.String(255), unique=True, index=True)
    status = db.Column(db.String(30), nullable=False, default='pending', index=True)
    paid_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    creator_account = db.relationship('CreatorAccount', backref=db.backref('platform_subscription_payments', lazy=True))
    subscription = db.relationship('PlatformSubscription', backref=db.backref('payments', lazy=True))


class CreatorPayoutAccount(db.Model):
    __tablename__ = 'creator_payout_accounts'
    id = db.Column(db.Integer, primary_key=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    provider = db.Column(db.String(30), nullable=False, default='paystack', index=True)
    provider_subaccount_code = db.Column(db.String(255), unique=True, index=True)
    business_name = db.Column(db.String(180))
    account_name = db.Column(db.String(180))
    settlement_bank = db.Column(db.String(180))
    account_number_last4 = db.Column(db.String(4))
    # Default for Free creators; paid plans use 3%. Do not trust this field
    # as the sole source of truth for transaction fee calculation.
    percentage_charge = db.Column(db.Numeric(5, 2), nullable=False, default=23)
    status = db.Column(db.String(30), nullable=False, default='pending', index=True)
    connected_at = db.Column(db.DateTime(timezone=True))
    disabled_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    creator_account = db.relationship('CreatorAccount', backref=db.backref('payout_account', uselist=False, cascade='all, delete-orphan', single_parent=True))


class CreatorProfile(db.Model):
    __tablename__ = 'creator_profiles'
    id = db.Column(db.Integer, primary_key=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), unique=True, index=True)
    display_name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    tagline = db.Column(db.String(255))
    bio = db.Column(db.Text)
    profile_image_url = db.Column(db.Text)
    profile_image_public_id = db.Column(db.String(500))
    intro_reel_url = db.Column(db.Text)
    intro_reel_public_id = db.Column(db.String(500))
    intro_reel_thumbnail_url = db.Column(db.Text)
    instagram_url = db.Column(db.Text)
    tiktok_url = db.Column(db.Text)
    youtube_url = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    creator_account = db.relationship('CreatorAccount', backref=db.backref('profile', uselist=False, cascade='all, delete-orphan', single_parent=True))


class ContentCategory(db.Model):
    __tablename__ = 'content_categories'
    id = db.Column(db.Integer, primary_key=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), index=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(120), nullable=False, index=True)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    creator_account = db.relationship('CreatorAccount', backref=db.backref('categories', lazy=True))
    __table_args__ = (db.UniqueConstraint('creator_account_id', 'slug', name='uq_content_category_creator_slug'),)


class ContentPost(db.Model):
    __tablename__ = 'content_posts'
    id = db.Column(db.Integer, primary_key=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('content_categories.id', ondelete='SET NULL'), index=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), nullable=False, index=True)
    excerpt = db.Column(db.Text)
    body = db.Column(db.Text)
    cover_image_url = db.Column(db.Text)
    content_type = db.Column(db.String(30), nullable=False, default='story', index=True)
    access_level = db.Column(db.String(30), nullable=False, default='public', index=True)
    status = db.Column(db.String(30), nullable=False, default='draft', index=True)
    is_featured = db.Column(db.Boolean, default=False, nullable=False)
    published_at = db.Column(db.DateTime(timezone=True), index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    category = db.relationship('ContentCategory', backref=db.backref('posts', lazy=True))
    creator_account = db.relationship('CreatorAccount', backref=db.backref('posts', lazy=True))
    __table_args__ = (db.UniqueConstraint('creator_account_id', 'slug', name='uq_content_post_creator_slug'),)



# ============================================================
# KALXA CREATOR
# CONTENT MEDIA MODEL
# ============================================================
#
# Supports:
#
# - Public media
# - Authenticated exclusive media
# - Cloudinary images and videos
# - Story galleries
# - Video thumbnails
# - Creator-specific content ownership through ContentPost
#
# Cloudinary delivery types:
#
# upload         = Public media
# authenticated  = Protected media
#
# IMPORTANT:
#
# media_url is nullable because authenticated media
# should not expose a permanent public URL.
#
# ============================================================
class ContentMedia(db.Model):

    __tablename__ = "content_media"

    # ========================================================
    # PRIMARY KEY
    # ========================================================

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # ========================================================
    # CONTENT POST
    # ========================================================

    post_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "content_posts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # ========================================================
    # MEDIA TYPE
    # ========================================================
    #
    # cover
    # video
    # gallery_image
    #
    # ========================================================

    media_type = db.Column(
        db.String(20),
        nullable=False,
    )

    # ========================================================
    # MEDIA URL
    # ========================================================
    #
    # Public:
    #   Stores the Cloudinary secure URL.
    #
    # Authenticated:
    #   NULL. Generate access URLs only after authorization.
    #
    # ========================================================

    media_url = db.Column(
        db.Text,
        nullable=True,
    )

    # ========================================================
    # CLOUDINARY PUBLIC ID
    # ========================================================

    public_id = db.Column(
        db.String(500),
        index=True,
    )

    # ========================================================
    # RESOURCE TYPE
    # ========================================================
    #
    # image
    # video
    #
    # ========================================================

    resource_type = db.Column(
        db.String(30),
    )

    # ========================================================
    # CLOUDINARY DELIVERY TYPE
    # ========================================================
    #
    # upload:
    #   Public Cloudinary delivery.
    #
    # authenticated:
    #   Cloudinary authenticated delivery.
    #
    # ========================================================

    delivery_type = db.Column(
        db.String(30),
        nullable=False,
        default="upload",
        server_default="upload",
        index=True,
    )

    # ========================================================
    # THUMBNAIL
    # ========================================================

    thumbnail_url = db.Column(
        db.Text,
    )

    # ========================================================
    # CAPTION
    # ========================================================

    caption = db.Column(
        db.String(255),
    )

    # ========================================================
    # MEDIA ORDER
    # ========================================================

    media_order = db.Column(
        db.Integer,
        default=0,
        nullable=False,
    )

    # ========================================================
    # VIDEO DURATION
    # ========================================================

    duration_seconds = db.Column(
        db.Float,
    )

    # ========================================================
    # IMAGE / VIDEO DIMENSIONS
    # ========================================================

    width = db.Column(
        db.Integer,
    )

    height = db.Column(
        db.Integer,
    )

    # ========================================================
    # CREATED AT
    # ========================================================

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # ========================================================
    # RELATIONSHIP
    # ========================================================

    post = db.relationship(
        "ContentPost",
        backref=db.backref(
            "media",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )


class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('content_posts.id', ondelete='CASCADE'), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('comments.id', ondelete='CASCADE'), index=True)
    author_name = db.Column(db.String(80), nullable=False)
    body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='approved', index=True)
    is_creator = db.Column(db.Boolean, default=False, nullable=False)
    anonymous_session_id = db.Column(db.String(100), index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    post = db.relationship('ContentPost', backref=db.backref('comments', lazy=True, cascade='all, delete-orphan'))
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy=True, cascade='all, delete-orphan', order_by='Comment.created_at.asc()')


class EmailSubscriber(db.Model):
    __tablename__ = 'email_subscribers'
    id = db.Column(db.Integer, primary_key=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), index=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    status = db.Column(db.String(30), default='pending', nullable=False, index=True)
    verification_token = db.Column(db.String(255), unique=True, index=True)
    unsubscribe_token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    verified_at = db.Column(db.DateTime(timezone=True))
    unsubscribed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    creator_account = db.relationship('CreatorAccount', backref=db.backref('email_subscribers', lazy=True))
    __table_args__ = (db.UniqueConstraint('creator_account_id', 'email', name='uq_email_subscriber_creator_email'),)


class EmailDelivery(db.Model):
    __tablename__ = 'email_deliveries'
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('email_subscribers.id', ondelete='SET NULL'), index=True)
    post_id = db.Column(db.Integer, db.ForeignKey('content_posts.id', ondelete='SET NULL'), index=True)
    email_type = db.Column(db.String(50), nullable=False, index=True)
    recipient_email = db.Column(db.String(255), nullable=False, index=True)
    subject = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), nullable=False, index=True)
    error_message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    subscriber = db.relationship('EmailSubscriber', backref=db.backref('deliveries', lazy=True))
    post = db.relationship('ContentPost', backref=db.backref('email_deliveries', lazy=True))


class FundraisingCampaign(db.Model):
    __tablename__ = 'fundraising_campaigns'
    id = db.Column(db.Integer, primary_key=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    cover_image_url = db.Column(db.Text)
    cover_image_public_id = db.Column(db.String(500))
    goal_amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default='ZAR')
    status = db.Column(db.String(30), nullable=False, default='draft', index=True)
    starts_at = db.Column(db.DateTime(timezone=True), index=True)
    ends_at = db.Column(db.DateTime(timezone=True), index=True)
    published_at = db.Column(db.DateTime(timezone=True), index=True)
    completed_at = db.Column(db.DateTime(timezone=True))
    cancelled_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    creator_account = db.relationship('CreatorAccount', backref=db.backref('fundraising_campaigns', lazy=True, cascade='all, delete-orphan'))
    __table_args__ = (db.UniqueConstraint('creator_account_id', 'slug', name='uq_fundraising_campaign_creator_slug'), db.CheckConstraint('goal_amount_cents > 0', name='ck_fundraising_campaign_positive_goal'))


class CreatorBranding(db.Model):
    __tablename__ = 'creator_brandings'
    id = db.Column(db.Integer, primary_key=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    site_title = db.Column(db.String(180))
    site_tagline = db.Column(db.String(255))
    logo_url = db.Column(db.Text)
    logo_public_id = db.Column(db.String(500))
    favicon_url = db.Column(db.Text)
    favicon_public_id = db.Column(db.String(500))
    cover_image_url = db.Column(db.Text)
    cover_image_public_id = db.Column(db.String(500))
    primary_color = db.Column(db.String(20), nullable=False, default='#111318')
    accent_color = db.Column(db.String(20), nullable=False, default='#d4a75d')
    background_color = db.Column(db.String(20), nullable=False, default='#ffffff')
    text_color = db.Column(db.String(20), nullable=False, default='#17191d')
    theme = db.Column(db.String(40), nullable=False, default='default')
    font_family = db.Column(db.String(80), nullable=False, default='system')
    footer_text = db.Column(db.String(255))
    show_platform_branding = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    creator_account = db.relationship('CreatorAccount', backref=db.backref('branding', uselist=False, cascade='all, delete-orphan', single_parent=True))


class CreatorDomain(db.Model):
    __tablename__ = 'creator_domains'
    id = db.Column(db.Integer, primary_key=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    hostname = db.Column(db.String(253), nullable=False, unique=True, index=True)
    domain_type = db.Column(db.String(30), nullable=False, default='subdomain', index=True)
    verification_status = db.Column(db.String(30), nullable=False, default='pending', index=True)
    verification_token = db.Column(db.String(255), unique=True)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=False, index=True)
    verified_at = db.Column(db.DateTime(timezone=True))
    activated_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    creator_account = db.relationship('CreatorAccount', backref=db.backref('domains', lazy=True, cascade='all, delete-orphan'))
    __table_args__ = (db.CheckConstraint("domain_type IN ('subdomain', 'custom')", name='ck_creator_domain_type'),)


class FanPayment(db.Model):
    __tablename__ = 'fan_payments'
    id = db.Column(db.Integer, primary_key=True)
    creator_account_id = db.Column(db.Integer, db.ForeignKey('creator_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('fundraising_campaigns.id', ondelete='SET NULL'), index=True)
    payment_type = db.Column(db.String(30), nullable=False, default='support', index=True)
    supporter_name = db.Column(db.String(120))
    supporter_email = db.Column(db.String(255), index=True)
    supporter_message = db.Column(db.String(500))
    is_anonymous = db.Column(db.Boolean, nullable=False, default=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default='ZAR')
    # Platform's 23% (Free) or 3% (paid) fee, stored per payment.
    platform_fee_cents = db.Column(db.Integer, nullable=False, default=0)
    provider = db.Column(db.String(30), nullable=False, default='paystack', index=True)
    provider_reference = db.Column(db.String(255), unique=True, index=True)
    provider_transaction_id = db.Column(db.String(255), unique=True, index=True)
    status = db.Column(db.String(30), nullable=False, default='pending', index=True)
    paid_at = db.Column(db.DateTime(timezone=True), index=True)
    failed_at = db.Column(db.DateTime(timezone=True))
    refunded_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    creator_account = db.relationship('CreatorAccount', backref=db.backref('fan_payments', lazy=True))
    campaign = db.relationship('FundraisingCampaign', backref=db.backref('payments', lazy=True))
    __table_args__ = (
        db.CheckConstraint('amount_cents > 0', name='ck_fan_payment_positive_amount'),
        db.CheckConstraint('platform_fee_cents >= 0', name='ck_fan_payment_nonnegative_platform_fee'),
        db.CheckConstraint('platform_fee_cents <= amount_cents', name='ck_fan_payment_fee_not_greater_than_amount'),
    )
