"""add platform subscriptions and payments

Revision ID: 47b9231e5dea
Revises: 1d55d4ae0b54
Create Date: 2026-10-07 00:50:17.991834

"""

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION IDENTIFIERS
# ============================================================

revision = "47b9231e5dea"
down_revision = "1d55d4ae0b54"
branch_labels = None
depends_on = None


# ============================================================
# DATETIME HELPERS
# ============================================================

def _normalise_datetime(value):
    """
    Return a Python datetime when possible.

    SQLite may return DateTime values as strings when executing
    raw SQL through Alembic, while PostgreSQL normally returns
    datetime objects.

    This keeps the backfill portable across both databases.
    """

    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):

        return value

    if isinstance(
        value,
        str,
    ):

        text = value.strip()

        if not text:
            return None

        # Handle a trailing UTC Z if encountered.
        if text.endswith("Z"):
            text = (
                text[:-1]
                + "+00:00"
            )

        try:
            return datetime.fromisoformat(
                text
            )

        except ValueError:
            pass

        # SQLite commonly stores datetimes using a space
        # between the date and time.
        formats = (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        )

        for date_format in formats:

            try:
                return datetime.strptime(
                    text,
                    date_format,
                )

            except ValueError:
                continue

    raise RuntimeError(
        "Unable to parse legacy subscription datetime."
    )


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
    #     plan
    #     subscription_status
    #     subscription_started_at
    #     subscription_expires_at
    #
    # We preserve those values by creating one
    # PlatformSubscription for each existing CreatorAccount.
    #
    # IMPORTANT:
    #
    # The previous migration used:
    #
    #     subscription_expires_at + INTERVAL '7 days'
    #
    # That syntax is PostgreSQL-specific and fails on SQLite.
    #
    # The backfill below calculates the grace date in Python
    # instead, allowing the same migration to run against:
    #
    #     SQLite development
    #     PostgreSQL / Neon production
    #
    # Existing creators without a recognised plan remain
    # Premium to preserve legacy functionality.
    # ========================================================

    connection = op.get_bind()


    # --------------------------------------------------------
    # REFLECT THE LEGACY CREATOR TABLE
    # --------------------------------------------------------
    #
    # Using SQLAlchemy's reflected column types is important.
    # It means SQLite DateTime values are converted through
    # SQLAlchemy rather than relying entirely on raw strings.
    # --------------------------------------------------------

    metadata = sa.MetaData()

    creator_accounts_table = sa.Table(
        "creator_accounts",
        metadata,
        autoload_with=connection,
    )

    platform_subscriptions_table = sa.Table(
        "platform_subscriptions",
        metadata,
        autoload_with=connection,
    )


    creator_rows = connection.execute(
        sa.select(
            creator_accounts_table.c.id,
            creator_accounts_table.c.plan,
            creator_accounts_table.c.subscription_status,
            creator_accounts_table.c.subscription_started_at,
            creator_accounts_table.c.subscription_expires_at,
        )
    ).mappings().all()


    valid_statuses = {
        "inactive",
        "active",
        "past_due",
        "expired",
        "cancelled",
    }


    for creator in creator_rows:

        creator_id = (
            creator["id"]
        )


        # ====================================================
        # IDEMPOTENCY
        # ====================================================

        existing_subscription = (
            connection.execute(
                sa.select(
                    platform_subscriptions_table.c.id
                )
                .where(
                    platform_subscriptions_table
                    .c
                    .creator_account_id
                    == creator_id
                )
                .limit(1)
            )
            .first()
        )

        if existing_subscription:
            continue


        # ====================================================
        # PLAN
        # ====================================================

        raw_plan = str(
            creator["plan"]
            or ""
        ).strip().lower()


        if raw_plan == "standard":

            plan = "standard"

        elif raw_plan == "premium":

            plan = "premium"

        else:

            # Preserve legacy functionality.
            plan = "premium"


        # ====================================================
        # STATUS
        # ====================================================

        raw_status = str(
            creator[
                "subscription_status"
            ]
            or ""
        ).strip().lower()


        if raw_status in valid_statuses:

            status = raw_status

        else:

            status = "inactive"


        # ====================================================
        # DATES
        # ====================================================

        started_at = _normalise_datetime(
            creator[
                "subscription_started_at"
            ]
        )

        expires_at = _normalise_datetime(
            creator[
                "subscription_expires_at"
            ]
        )


        grace_period_ends_at = None
        cancelled_at = None


        if (
            status == "past_due"
            and expires_at is not None
        ):

            grace_period_ends_at = (
                expires_at
                + timedelta(days=7)
            )


        if status == "cancelled":

            cancelled_at = (
                expires_at
                or datetime.now(
                    timezone.utc
                )
            )


        now = datetime.now(
            timezone.utc
        )


        # ====================================================
        # INSERT SUBSCRIPTION
        # ====================================================

        connection.execute(
            platform_subscriptions_table.insert().values(
                creator_account_id=creator_id,

                plan=plan,

                status=status,

                provider="legacy",

                provider_subscription_id=None,

                started_at=started_at,

                current_period_start=started_at,

                current_period_end=expires_at,

                grace_period_ends_at=(
                    grace_period_ends_at
                ),

                cancelled_at=cancelled_at,

                created_at=now,

                updated_at=now,
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
