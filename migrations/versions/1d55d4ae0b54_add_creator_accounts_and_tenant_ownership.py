"""add creator accounts and tenant ownership

Revision ID: 1d55d4ae0b54
Revises: 486565da0bd1
Create Date: 2026-10-05 08:18:22.804408

"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# ALEMBIC REVISION IDENTIFIERS
# ============================================================

revision = "1d55d4ae0b54"
down_revision = "486565da0bd1"
branch_labels = None
depends_on = None


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    # ========================================================
    # CREATOR ACCOUNTS
    # ========================================================
    #
    # This is the SaaS tenant/account table.
    #
    # Existing creator data is NOT migrated into this table
    # here. That will be handled separately by a controlled
    # backfill after the schema has been created.
    #
    # For that reason, creator_account_id remains nullable on
    # existing tables during this migration.
    #
    # Existing/legacy creators default to Premium so that
    # introducing SaaS plans does not unexpectedly remove
    # functionality from the original creator.
    # ========================================================

    op.create_table(
        "creator_accounts",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "username",
            sa.String(length=80),
            nullable=False,
        ),

        sa.Column(
            "email",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "password_hash",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "plan",
            sa.String(length=30),
            nullable=False,
            server_default="premium",
        ),

        sa.Column(
            "account_status",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "payment_status",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "registration_paid_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "subscription_status",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "subscription_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "subscription_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "last_login_at",
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

        sa.PrimaryKeyConstraint(
            "id",
        ),
    )

    # ========================================================
    # CREATOR ACCOUNT INDEXES
    # ========================================================

    op.create_index(
        "ix_creator_accounts_account_status",
        "creator_accounts",
        ["account_status"],
        unique=False,
    )

    op.create_index(
        "ix_creator_accounts_email",
        "creator_accounts",
        ["email"],
        unique=True,
    )

    op.create_index(
        "ix_creator_accounts_payment_status",
        "creator_accounts",
        ["payment_status"],
        unique=False,
    )

    op.create_index(
        "ix_creator_accounts_subscription_expires_at",
        "creator_accounts",
        ["subscription_expires_at"],
        unique=False,
    )

    op.create_index(
        "ix_creator_accounts_subscription_status",
        "creator_accounts",
        ["subscription_status"],
        unique=False,
    )

    op.create_index(
        "ix_creator_accounts_username",
        "creator_accounts",
        ["username"],
        unique=True,
    )

    # ========================================================
    # CONTENT CATEGORIES
    # ========================================================

    op.add_column(
        "content_categories",
        sa.Column(
            "creator_account_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_content_categories_creator_account_id",
        "content_categories",
        ["creator_account_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_content_categories_creator_account_id",
        "content_categories",
        "creator_accounts",
        ["creator_account_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ========================================================
    # CONTENT POSTS
    # ========================================================

    op.add_column(
        "content_posts",
        sa.Column(
            "creator_account_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_content_posts_creator_account_id",
        "content_posts",
        ["creator_account_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_content_posts_creator_account_id",
        "content_posts",
        "creator_accounts",
        ["creator_account_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ========================================================
    # CREATOR PROFILES
    # ========================================================

    op.add_column(
        "creator_profiles",
        sa.Column(
            "creator_account_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # One profile per creator account.
    op.create_index(
        "ix_creator_profiles_creator_account_id",
        "creator_profiles",
        ["creator_account_id"],
        unique=True,
    )

    op.create_foreign_key(
        "fk_creator_profiles_creator_account_id",
        "creator_profiles",
        "creator_accounts",
        ["creator_account_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ========================================================
    # EMAIL SUBSCRIBERS
    # ========================================================
    #
    # Previously:
    #
    #     email was globally unique.
    #
    # SaaS behavior:
    #
    #     the same email may subscribe to Creator A
    #     and Creator B.
    #
    # But the same email cannot subscribe twice to the
    # same creator.
    #
    # Therefore uniqueness becomes:
    #
    #     creator_account_id + email
    #
    # verification_token and unsubscribe_token remain
    # globally unique.
    # ========================================================

    op.add_column(
        "email_subscribers",
        sa.Column(
            "creator_account_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # Remove old globally unique email index.
    op.drop_index(
        "ix_email_subscribers_email",
        table_name="email_subscribers",
    )

    # Re-create email as a normal lookup index.
    op.create_index(
        "ix_email_subscribers_email",
        "email_subscribers",
        ["email"],
        unique=False,
    )

    op.create_index(
        "ix_email_subscribers_creator_account_id",
        "email_subscribers",
        ["creator_account_id"],
        unique=False,
    )

    # Same email can exist for multiple creators,
    # but only once per individual creator.
    op.create_unique_constraint(
        "uq_email_subscriber_creator_email",
        "email_subscribers",
        [
            "creator_account_id",
            "email",
        ],
    )

    op.create_foreign_key(
        "fk_email_subscribers_creator_account_id",
        "email_subscribers",
        "creator_accounts",
        ["creator_account_id"],
        ["id"],
        ondelete="CASCADE",
    )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():

    # ========================================================
    # EMAIL SUBSCRIBERS
    # ========================================================

    op.drop_constraint(
        "fk_email_subscribers_creator_account_id",
        "email_subscribers",
        type_="foreignkey",
    )

    op.drop_constraint(
        "uq_email_subscriber_creator_email",
        "email_subscribers",
        type_="unique",
    )

    op.drop_index(
        "ix_email_subscribers_creator_account_id",
        table_name="email_subscribers",
    )

    op.drop_index(
        "ix_email_subscribers_email",
        table_name="email_subscribers",
    )

    # Restore original globally unique email index.
    op.create_index(
        "ix_email_subscribers_email",
        "email_subscribers",
        ["email"],
        unique=True,
    )

    op.drop_column(
        "email_subscribers",
        "creator_account_id",
    )

    # ========================================================
    # CREATOR PROFILES
    # ========================================================

    op.drop_constraint(
        "fk_creator_profiles_creator_account_id",
        "creator_profiles",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_creator_profiles_creator_account_id",
        table_name="creator_profiles",
    )

    op.drop_column(
        "creator_profiles",
        "creator_account_id",
    )

    # ========================================================
    # CONTENT POSTS
    # ========================================================

    op.drop_constraint(
        "fk_content_posts_creator_account_id",
        "content_posts",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_content_posts_creator_account_id",
        table_name="content_posts",
    )

    op.drop_column(
        "content_posts",
        "creator_account_id",
    )

    # ========================================================
    # CONTENT CATEGORIES
    # ========================================================

    op.drop_constraint(
        "fk_content_categories_creator_account_id",
        "content_categories",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_content_categories_creator_account_id",
        table_name="content_categories",
    )

    op.drop_column(
        "content_categories",
        "creator_account_id",
    )

    # ========================================================
    # CREATOR ACCOUNTS
    # ========================================================

    op.drop_index(
        "ix_creator_accounts_username",
        table_name="creator_accounts",
    )

    op.drop_index(
        "ix_creator_accounts_subscription_status",
        table_name="creator_accounts",
    )

    op.drop_index(
        "ix_creator_accounts_subscription_expires_at",
        table_name="creator_accounts",
    )

    op.drop_index(
        "ix_creator_accounts_payment_status",
        table_name="creator_accounts",
    )

    op.drop_index(
        "ix_creator_accounts_email",
        table_name="creator_accounts",
    )

    op.drop_index(
        "ix_creator_accounts_account_status",
        table_name="creator_accounts",
    )

    op.drop_table(
        "creator_accounts",
    )
