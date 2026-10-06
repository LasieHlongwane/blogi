"""add platform subscriptions and payments

Revision ID: 47b9231e5dea
Revises: 486565da0bd1
Create Date: 2026-10-07 00:50:17.991834

"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION IDENTIFIERS
# ============================================================

revision = "47b9231e5dea"
down_revision = "486565da0bd1"
branch_labels = None
depends_on = None


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    # ========================================================
    # PLATFORM SUBSCRIPTIONS
    # ========================================================

    op.create_table(
        "platform_subscriptions",

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
            "plan",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "provider",
            sa.String(length=30),
            nullable=True,
        ),

        sa.Column(
            "provider_subscription_id",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "current_period_start",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "current_period_end",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "grace_period_ends_at",
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

        sa.ForeignKeyConstraint(
            ["creator_account_id"],
            ["creator_accounts.id"],
            name=(
                "fk_platform_subscriptions_"
                "creator_account_id"
            ),
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),

        sa.UniqueConstraint(
            "creator_account_id",
            name=(
                "uq_platform_subscriptions_"
                "creator_account_id"
            ),
        ),

        sa.UniqueConstraint(
            "provider_subscription_id",
            name=(
                "uq_platform_subscriptions_"
                "provider_subscription_id"
            ),
        ),
    )


    # ========================================================
    # PLATFORM SUBSCRIPTION INDEXES
    # ========================================================

    op.create_index(
        "ix_platform_subscriptions_creator_account_id",
        "platform_subscriptions",
        ["creator_account_id"],
        unique=True,
    )

    op.create_index(
        "ix_platform_subscriptions_plan",
        "platform_subscriptions",
        ["plan"],
        unique=False,
    )

    op.create_index(
        "ix_platform_subscriptions_status",
        "platform_subscriptions",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_platform_subscriptions_provider",
        "platform_subscriptions",
        ["provider"],
        unique=False,
    )

    op.create_index(
        "ix_platform_subscriptions_provider_subscription_id",
        "platform_subscriptions",
        ["provider_subscription_id"],
        unique=True,
    )

    op.create_index(
        "ix_platform_subscriptions_current_period_end",
        "platform_subscriptions",
        ["current_period_end"],
        unique=False,
    )

    op.create_index(
        "ix_platform_subscriptions_grace_period_ends_at",
        "platform_subscriptions",
        ["grace_period_ends_at"],
        unique=False,
    )


    # ========================================================
    # PLATFORM SUBSCRIPTION PAYMENTS
    # ========================================================

    op.create_table(
        "platform_subscription_payments",

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
            "subscription_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "plan",
            sa.String(length=30),
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
                "fk_platform_subscription_payments_"
                "creator_account_id"
            ),
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["platform_subscriptions.id"],
            name=(
                "fk_platform_subscription_payments_"
                "subscription_id"
            ),
            ondelete="SET NULL",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),

        sa.UniqueConstraint(
            "provider_reference",
            name=(
                "uq_platform_subscription_payments_"
                "provider_reference"
            ),
        ),
    )


    # ========================================================
    # PAYMENT INDEXES
    # ========================================================

    op.create_index(
        "ix_platform_subscription_payments_creator_account_id",
        "platform_subscription_payments",
        ["creator_account_id"],
        unique=False,
    )

    op.create_index(
        "ix_platform_subscription_payments_subscription_id",
        "platform_subscription_payments",
        ["subscription_id"],
        unique=False,
    )

    op.create_index(
        "ix_platform_subscription_payments_plan",
        "platform_subscription_payments",
        ["plan"],
        unique=False,
    )

    op.create_index(
        "ix_platform_subscription_payments_provider",
        "platform_subscription_payments",
        ["provider"],
        unique=False,
    )

    op.create_index(
        "ix_platform_subscription_payments_provider_reference",
        "platform_subscription_payments",
        ["provider_reference"],
        unique=True,
    )

    op.create_index(
        "ix_platform_subscription_payments_status",
        "platform_subscription_payments",
        ["status"],
        unique=False,
    )


    # ========================================================
    # BACKFILL EXISTING CREATOR SUBSCRIPTIONS
    # ========================================================
    #
    # CreatorAccount currently contains the legacy fields:
    #
    # plan
    # subscription_status
    # subscription_started_at
    # subscription_expires_at
    #
    # We preserve those values by creating one
    # PlatformSubscription for every existing creator.
    #
    # Existing creators without a valid plan are treated as
    # Premium to preserve legacy functionality.
    #
    # The legacy CreatorAccount fields are NOT removed during
    # Stage 2 because the application temporarily keeps them
    # synchronized.
    # ========================================================

    op.execute(
        sa.text(
            """
            INSERT INTO platform_subscriptions
            (
                creator_account_id,
                plan,
                status,
                provider,
                provider_subscription_id,
                started_at,
                current_period_start,
                current_period_end,
                grace_period_ends_at,
                cancelled_at,
                created_at,
                updated_at
            )
            SELECT
                id,

                CASE
                    WHEN LOWER(COALESCE(plan, '')) = 'standard'
                        THEN 'standard'

                    WHEN LOWER(COALESCE(plan, '')) = 'premium'
                        THEN 'premium'

                    ELSE 'premium'
                END,

                CASE
                    WHEN subscription_status IN (
                        'inactive',
                        'active',
                        'past_due',
                        'expired',
                        'cancelled'
                    )
                        THEN subscription_status

                    ELSE 'inactive'
                END,

                'legacy',

                NULL,

                subscription_started_at,

                subscription_started_at,

                subscription_expires_at,

                CASE
                    WHEN subscription_status = 'past_due'
                         AND subscription_expires_at IS NOT NULL
                    THEN subscription_expires_at
                         + INTERVAL '7 days'

                    ELSE NULL
                END,

                CASE
                    WHEN subscription_status = 'cancelled'
                    THEN COALESCE(
                        subscription_expires_at,
                        CURRENT_TIMESTAMP
                    )

                    ELSE NULL
                END,

                CURRENT_TIMESTAMP,

                CURRENT_TIMESTAMP

            FROM creator_accounts

            WHERE NOT EXISTS
            (
                SELECT 1

                FROM platform_subscriptions ps

                WHERE
                    ps.creator_account_id
                    = creator_accounts.id
            );
            """
        )
    )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():

    # ========================================================
    # DROP PAYMENT INDEXES
    # ========================================================

    op.drop_index(
        "ix_platform_subscription_payments_status",
        table_name="platform_subscription_payments",
    )

    op.drop_index(
        "ix_platform_subscription_payments_provider_reference",
        table_name="platform_subscription_payments",
    )

    op.drop_index(
        "ix_platform_subscription_payments_provider",
        table_name="platform_subscription_payments",
    )

    op.drop_index(
        "ix_platform_subscription_payments_plan",
        table_name="platform_subscription_payments",
    )

    op.drop_index(
        "ix_platform_subscription_payments_subscription_id",
        table_name="platform_subscription_payments",
    )

    op.drop_index(
        "ix_platform_subscription_payments_creator_account_id",
        table_name="platform_subscription_payments",
    )


    # ========================================================
    # DROP PAYMENT TABLE
    # ========================================================

    op.drop_table(
        "platform_subscription_payments"
    )


    # ========================================================
    # DROP SUBSCRIPTION INDEXES
    # ========================================================

    op.drop_index(
        "ix_platform_subscriptions_grace_period_ends_at",
        table_name="platform_subscriptions",
    )

    op.drop_index(
        "ix_platform_subscriptions_current_period_end",
        table_name="platform_subscriptions",
    )

    op.drop_index(
        "ix_platform_subscriptions_provider_subscription_id",
        table_name="platform_subscriptions",
    )

    op.drop_index(
        "ix_platform_subscriptions_provider",
        table_name="platform_subscriptions",
    )

    op.drop_index(
        "ix_platform_subscriptions_status",
        table_name="platform_subscriptions",
    )

    op.drop_index(
        "ix_platform_subscriptions_plan",
        table_name="platform_subscriptions",
    )

    op.drop_index(
        "ix_platform_subscriptions_creator_account_id",
        table_name="platform_subscriptions",
    )


    # ========================================================
    # DROP SUBSCRIPTION TABLE
    # ========================================================

    op.drop_table(
        "platform_subscriptions"
    )