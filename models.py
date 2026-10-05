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
# This is the SaaS tenant/account.
#
# Every creator who registers gets one CreatorAccount.
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
    #
    # Existing creator accounts should migrate to Premium
    # so that current functionality is not unexpectedly lost.
    #
    # New registrations explicitly choose Standard/Premium
    # inside creator_auth.py.
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
    # REGISTRATION / INITIAL PLATFORM PAYMENT
    # ========================================================
    #
    # This remains for the current manual MVP flow.
    #
    # Later Yoco will become the source of truth for the
    # creator -> Kalxa platform payment.
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
    # MONTHLY SAAS SUBSCRIPTION
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
# CREATOR PROFILE
# ============================================================

class CreatorProfile(db.Model):

    __tablename__ = "creator_profiles"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # ========================================================
    # SAAS OWNER
    # ========================================================
    #
    # Temporarily nullable for migration/backfill.
    # Later this becomes nullable=False.
    # ========================================================

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

    # ========================================================
    # RELATIONSHIP
    # ========================================================

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

    # ========================================================
    # SAAS OWNER
    # ========================================================

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

    # ========================================================
    # TENANT-SCOPED SLUG
    # ========================================================
    #
    # Slug is NOT globally unique anymore.
    #
    # Two different creators may both have:
    #
    #   /@creator-a/category/travel
    #   /@creator-b/category/travel
    #
    # Uniqueness is enforced by the composite constraint
    # declared in __table_args__ below.
    # ========================================================

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

    # ========================================================
    # RELATIONSHIP
    # ========================================================

    creator_account = db.relationship(
        "CreatorAccount",
        backref=db.backref(
            "categories",
            lazy=True,
        ),
    )

    # ========================================================
    # MULTI-TENANT UNIQUE CONSTRAINT
    # ========================================================

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

    # ========================================================
    # SAAS OWNER
    # ========================================================

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

    # ========================================================
    # TENANT-SCOPED SLUG
    # ========================================================
    #
    # Slug is NOT globally unique.
    #
    # These are both valid:
    #
    #   /@creator-a/content/my-first-vlog
    #   /@creator-b/content/my-first-vlog
    #
    # The creator + slug combination is unique.
    # ========================================================

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

    # ========================================================
    # RELATIONSHIPS
    # ========================================================

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

    # ========================================================
    # MULTI-TENANT UNIQUE CONSTRAINT
    # ========================================================

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

    # ========================================================
    # CLOUDINARY
    # ========================================================

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

    # ========================================================
    # MEDIA DETAILS
    # ========================================================

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

    # ========================================================
    # RELATIONSHIPS
    # ========================================================

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
#
# A visitor can subscribe separately to multiple creators.
#
# Therefore email is no longer globally unique.
# Instead:
#
# creator_account_id + email
#
# must be unique.
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

    # ========================================================
    # RELATIONSHIP
    # ========================================================

    creator_account = db.relationship(
        "CreatorAccount",
        backref=db.backref(
            "email_subscribers",
            lazy=True,
        ),
    )

    # ========================================================
    # MULTI-TENANT UNIQUE CONSTRAINT
    # ========================================================

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
