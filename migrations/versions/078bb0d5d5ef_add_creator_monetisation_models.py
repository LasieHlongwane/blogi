"""add creator monetisation models

Revision ID: 078bb0d5d5ef
Revises: 47b9231e5dea
Create Date: 2026-10-08 00:12:13.232778

"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# ALEMBIC REVISION IDENTIFIERS
# ============================================================

revision = "078bb0d5d5ef"
down_revision = "47b9231e5dea"
branch_labels = None
depends_on = None


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    # ========================================================
    # CREATOR PAYOUT ACCOUNTS
    # ========================================================
    #
    # One payout configuration per creator.
    #
    # IMPORTANT:
    #
    # We deliberately store only:
    #
    # - Paystack subaccount code
    # - account holder/business names
    # - settlement bank name
    # - final four account-number digits
    #
    # Full bank-account details must not be persisted here.
    # ========================================================

    op.create_table(
        "creator_payout_accounts",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "creator_account_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "provider",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "provider_subaccount_code",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "business_name",
            sa.String(length=180),
            nullable=True,
        ),

        sa.Column(
            "account_name",
            sa.String(length=180),
            nullable=True,
        ),

        sa.Column(
            "settlement_bank",
            sa.String(length=180),
            nullable=True,
        ),

        sa.Column(
            "account_number_last4",
            sa.String(length=4),
            nullable=True,
        ),

        sa.Column(
            "percentage_charge",
            sa.Numeric(
                precision=5,
                scale=2,
            ),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "connected_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "disabled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["creator_account_id"],
            ["creator_accounts.id"],
            name=(
                "fk_creator_payout_accounts_"
                "creator_account_id"
            ),
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),
    )


    # ========================================================
    # CREATOR PAYOUT ACCOUNT INDEXES
    # ========================================================

    op.create_index(
        "ix_creator_payout_accounts_creator_account_id",
        "creator_payout_accounts",
        ["creator_account_id"],
        unique=True,
    )

    op.create_index(
        "ix_creator_payout_accounts_provider",
        "creator_payout_accounts",
        ["provider"],
        unique=False,
    )

    op.create_index(
        "ix_creator_payout_accounts_provider_subaccount_code",
        "creator_payout_accounts",
        ["provider_subaccount_code"],
        unique=True,
    )

    op.create_index(
        "ix_creator_payout_accounts_status",
        "creator_payout_accounts",
        ["status"],
        unique=False,
    )


    # ========================================================
    # FUNDRAISING CAMPAIGNS
    # ========================================================
    #
    # Premium creators can create fundraising campaigns.
    #
    # The amount raised is intentionally NOT stored here.
    #
    # Successful FanPayment rows remain the source of truth
    # for campaign revenue.
    # ========================================================

    op.create_table(
        "fundraising_campaigns",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "creator_account_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "title",
            sa.String(length=180),
            nullable=False,
        ),

        sa.Column(
            "slug",
            sa.String(length=200),
            nullable=False,
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "cover_image_url",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "cover_image_public_id",
            sa.String(length=500),
            nullable=True,
        ),

        sa.Column(
            "goal_amount_cents",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "currency",
            sa.String(length=10),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "starts_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "ends_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.CheckConstraint(
            "goal_amount_cents > 0",
            name=(
                "ck_fundraising_campaign_"
                "positive_goal"
            ),
        ),

        sa.ForeignKeyConstraint(
            ["creator_account_id"],
            ["creator_accounts.id"],
            name=(
                "fk_fundraising_campaigns_"
                "creator_account_id"
            ),
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),

        sa.UniqueConstraint(
            "creator_account_id",
            "slug",
            name=(
                "uq_fundraising_campaign_"
                "creator_slug"
            ),
        ),
    )


    # ========================================================
    # FUNDRAISING CAMPAIGN INDEXES
    # ========================================================

    op.create_index(
        "ix_fundraising_campaigns_creator_account_id",
        "fundraising_campaigns",
        ["creator_account_id"],
        unique=False,
    )

    op.create_index(
        "ix_fundraising_campaigns_ends_at",
        "fundraising_campaigns",
        ["ends_at"],
        unique=False,
    )

    op.create_index(
        "ix_fundraising_campaigns_published_at",
        "fundraising_campaigns",
        ["published_at"],
        unique=False,
    )

    op.create_index(
        "ix_fundraising_campaigns_slug",
        "fundraising_campaigns",
        ["slug"],
        unique=False,
    )

    op.create_index(
        "ix_fundraising_campaigns_starts_at",
        "fundraising_campaigns",
        ["starts_at"],
        unique=False,
    )

    op.create_index(
        "ix_fundraising_campaigns_status",
        "fundraising_campaigns",
        ["status"],
        unique=False,
    )


    # ========================================================
    # FAN PAYMENTS
    # ========================================================
    #
    # Represents money sent from a fan to a creator.
    #
    # Supported payment types:
    #
    #   support
    #   campaign
    #   membership
    #
    # FanPayment is also our payment audit record.
    #
    # IMPORTANT:
    #
    # Browser redirects must NEVER be trusted to change a
    # payment to "paid".
    #
    # Paid status must only be applied after provider webhook
    # verification / server-side transaction verification.
    # ========================================================

    op.create_table(
        "fan_payments",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "creator_account_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "campaign_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "payment_type",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "supporter_name",
            sa.String(length=120),
            nullable=True,
        ),

        sa.Column(
            "supporter_email",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "supporter_message",
            sa.String(length=500),
            nullable=True,
        ),

        sa.Column(
            "is_anonymous",
            sa.Boolean(),
            nullable=False,
        ),

        sa.Column(
            "amount_cents",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "currency",
            sa.String(length=10),
            nullable=False,
        ),

        sa.Column(
            "platform_fee_cents",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "provider",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "provider_reference",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "provider_transaction_id",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "refunded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.CheckConstraint(
            "amount_cents > 0",
            name=(
                "ck_fan_payment_positive_amount"
            ),
        ),

        sa.CheckConstraint(
            "platform_fee_cents >= 0",
            name=(
                "ck_fan_payment_nonnegative_platform_fee"
            ),
        ),

        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["fundraising_campaigns.id"],
            name=(
                "fk_fan_payments_campaign_id"
            ),
            ondelete="SET NULL",
        ),

        sa.ForeignKeyConstraint(
            ["creator_account_id"],
            ["creator_accounts.id"],
            name=(
                "fk_fan_payments_creator_account_id"
            ),
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),
    )


    # ========================================================
    # FAN PAYMENT INDEXES
    # ========================================================

    op.create_index(
        "ix_fan_payments_campaign_id",
        "fan_payments",
        ["campaign_id"],
        unique=False,
    )

    op.create_index(
        "ix_fan_payments_created_at",
        "fan_payments",
        ["created_at"],
        unique=False,
    )

    op.create_index(
        "ix_fan_payments_creator_account_id",
        "fan_payments",
        ["creator_account_id"],
        unique=False,
    )

    op.create_index(
        "ix_fan_payments_paid_at",
        "fan_payments",
        ["paid_at"],
        unique=False,
    )

    op.create_index(
        "ix_fan_payments_payment_type",
        "fan_payments",
        ["payment_type"],
        unique=False,
    )

    op.create_index(
        "ix_fan_payments_provider",
        "fan_payments",
        ["provider"],
        unique=False,
    )

    # Provider references must be unique.
    #
    # Multiple NULL values remain valid on both SQLite and
    # PostgreSQL, while a real provider reference cannot be
    # recorded twice.
    op.create_index(
        "ix_fan_payments_provider_reference",
        "fan_payments",
        ["provider_reference"],
        unique=True,
    )

    op.create_index(
        "ix_fan_payments_provider_transaction_id",
        "fan_payments",
        ["provider_transaction_id"],
        unique=True,
    )

    op.create_index(
        "ix_fan_payments_status",
        "fan_payments",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_fan_payments_supporter_email",
        "fan_payments",
        ["supporter_email"],
        unique=False,
    )


    # ========================================================
    # CONTENT CATEGORY TENANT-SCOPED SLUGS
    # ========================================================
    #
    # Previously category slugs were globally unique.
    #
    # In a multi-creator platform:
    #
    # Creator A may have:
    #     /stories
    #
    # Creator B may also have:
    #     /stories
    #
    # Therefore uniqueness must be:
    #
    #     creator_account_id + slug
    # ========================================================

    with op.batch_alter_table(
        "content_categories",
        schema=None,
    ) as batch_op:

        batch_op.drop_index(
            "ix_content_categories_slug"
        )

        batch_op.create_index(
            "ix_content_categories_slug",
            ["slug"],
            unique=False,
        )

        batch_op.create_unique_constraint(
            "uq_content_category_creator_slug",
            [
                "creator_account_id",
                "slug",
            ],
        )


    # ========================================================
    # CONTENT POST TENANT-SCOPED SLUGS
    # ========================================================

    with op.batch_alter_table(
        "content_posts",
        schema=None,
    ) as batch_op:

        batch_op.drop_index(
            "ix_content_posts_slug"
        )

        batch_op.create_index(
            "ix_content_posts_slug",
            ["slug"],
            unique=False,
        )

        batch_op.create_unique_constraint(
            "uq_content_post_creator_slug",
            [
                "creator_account_id",
                "slug",
            ],
        )


    # ========================================================
    # CREATOR PLAN INDEX
    # ========================================================

    op.create_index(
        "ix_creator_accounts_plan",
        "creator_accounts",
        ["plan"],
        unique=False,
    )


    # ========================================================
    # IMPORTANT: EXISTING PAYMENT CONSTRAINTS
    # ========================================================
    #
    # The autogenerated migration attempted to DROP:
    #
    # uq_platform_subscription_payments_provider_reference
    #
    # uq_platform_subscriptions_creator_account_id
    #
    # uq_platform_subscriptions_provider_subscription_id
    #
    # We deliberately DO NOT drop them.
    #
    # creator_account_id must remain one-to-one with
    # PlatformSubscription.
    #
    # Provider subscription IDs and payment references are
    # external payment identifiers and should remain unique.
    #
    # Removing these constraints could permit duplicate payment
    # processing or duplicate subscription ownership.
    # ========================================================


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():

    # ========================================================
    # CREATOR PLAN INDEX
    # ========================================================

    op.drop_index(
        "ix_creator_accounts_plan",
        table_name="creator_accounts",
    )


    # ========================================================
    # CONTENT POSTS
    # ========================================================

    with op.batch_alter_table(
        "content_posts",
        schema=None,
    ) as batch_op:

        batch_op.drop_constraint(
            "uq_content_post_creator_slug",
            type_="unique",
        )

        batch_op.drop_index(
            "ix_content_posts_slug"
        )

        batch_op.create_index(
            "ix_content_posts_slug",
            ["slug"],
            unique=True,
        )


    # ========================================================
    # CONTENT CATEGORIES
    # ========================================================

    with op.batch_alter_table(
        "content_categories",
        schema=None,
    ) as batch_op:

        batch_op.drop_constraint(
            "uq_content_category_creator_slug",
            type_="unique",
        )

        batch_op.drop_index(
            "ix_content_categories_slug"
        )

        batch_op.create_index(
            "ix_content_categories_slug",
            ["slug"],
            unique=True,
        )


    # ========================================================
    # FAN PAYMENT INDEXES
    # ========================================================

    op.drop_index(
        "ix_fan_payments_supporter_email",
        table_name="fan_payments",
    )

    op.drop_index(
        "ix_fan_payments_status",
        table_name="fan_payments",
    )

    op.drop_index(
        "ix_fan_payments_provider_transaction_id",
        table_name="fan_payments",
    )

    op.drop_index(
        "ix_fan_payments_provider_reference",
        table_name="fan_payments",
    )

    op.drop_index(
        "ix_fan_payments_provider",
        table_name="fan_payments",
    )

    op.drop_index(
        "ix_fan_payments_payment_type",
        table_name="fan_payments",
    )

    op.drop_index(
        "ix_fan_payments_paid_at",
        table_name="fan_payments",
    )

    op.drop_index(
        "ix_fan_payments_creator_account_id",
        table_name="fan_payments",
    )

    op.drop_index(
        "ix_fan_payments_created_at",
        table_name="fan_payments",
    )

    op.drop_index(
        "ix_fan_payments_campaign_id",
        table_name="fan_payments",
    )


    # ========================================================
    # FAN PAYMENTS
    # ========================================================

    op.drop_table(
        "fan_payments"
    )


    # ========================================================
    # FUNDRAISING CAMPAIGN INDEXES
    # ========================================================

    op.drop_index(
        "ix_fundraising_campaigns_status",
        table_name="fundraising_campaigns",
    )

    op.drop_index(
        "ix_fundraising_campaigns_starts_at",
        table_name="fundraising_campaigns",
    )

    op.drop_index(
        "ix_fundraising_campaigns_slug",
        table_name="fundraising_campaigns",
    )

    op.drop_index(
        "ix_fundraising_campaigns_published_at",
        table_name="fundraising_campaigns",
    )

    op.drop_index(
        "ix_fundraising_campaigns_ends_at",
        table_name="fundraising_campaigns",
    )

    op.drop_index(
        "ix_fundraising_campaigns_creator_account_id",
        table_name="fundraising_campaigns",
    )


    # ========================================================
    # FUNDRAISING CAMPAIGNS
    # ========================================================

    op.drop_table(
        "fundraising_campaigns"
    )


    # ========================================================
    # CREATOR PAYOUT ACCOUNT INDEXES
    # ========================================================

    op.drop_index(
        "ix_creator_payout_accounts_status",
        table_name="creator_payout_accounts",
    )

    op.drop_index(
        "ix_creator_payout_accounts_provider_subaccount_code",
        table_name="creator_payout_accounts",
    )

    op.drop_index(
        "ix_creator_payout_accounts_provider",
        table_name="creator_payout_accounts",
    )

    op.drop_index(
        "ix_creator_payout_accounts_creator_account_id",
        table_name="creator_payout_accounts",
    )


    # ========================================================
    # CREATOR PAYOUT ACCOUNTS
    # ========================================================

    op.drop_table(
        "creator_payout_accounts"
    )