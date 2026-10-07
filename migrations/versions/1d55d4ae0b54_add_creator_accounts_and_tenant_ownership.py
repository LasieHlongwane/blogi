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
    # Existing creator data is NOT assigned to a creator
    # account here. That remains a controlled backfill.
    #
    # Existing tenant-owned tables therefore receive a
    # nullable creator_account_id.
    #
    # Existing/legacy creators default to Premium so the SaaS
    # migration does not unexpectedly remove functionality.
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
    #
    # batch_alter_table is intentionally used here.
    #
    # SQLite cannot add foreign-key constraints to an existing
    # table with ALTER TABLE in the same way PostgreSQL can.
    # Alembic batch mode safely rebuilds the table on SQLite.
    # ========================================================

    with op.batch_alter_table(
        "content_categories",
        schema=None,
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                "creator_account_id",
                sa.Integer(),
                nullable=True,
            )
        )

        batch_op.create_index(
            "ix_content_categories_creator_account_id",
            ["creator_account_id"],
            unique=False,
        )

        batch_op.create_foreign_key(
            "fk_content_categories_creator_account_id",
            "creator_accounts",
            ["creator_account_id"],
            ["id"],
            ondelete="CASCADE",
        )


    # ========================================================
    # CONTENT POSTS
    # ========================================================

    with op.batch_alter_table(
        "content_posts",
        schema=None,
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                "creator_account_id",
                sa.Integer(),
                nullable=True,
            )
        )

        batch_op.create_index(
            "ix_content_posts_creator_account_id",
            ["creator_account_id"],
            unique=False,
        )

        batch_op.create_foreign_key(
            "fk_content_posts_creator_account_id",
            "creator_accounts",
            ["creator_account_id"],
            ["id"],
            ondelete="CASCADE",
        )


    # ========================================================
    # CREATOR PROFILES
    # ========================================================

    with op.batch_alter_table(
        "creator_profiles",
        schema=None,
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                "creator_account_id",
                sa.Integer(),
                nullable=True,
            )
        )

        # One profile per creator account.
        batch_op.create_index(
            "ix_creator_profiles_creator_account_id",
            ["creator_account_id"],
            unique=True,
        )

        batch_op.create_foreign_key(
            "fk_creator_profiles_creator_account_id",
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
    #     the same email can subscribe to multiple creators.
    #
    # But:
    #
    #     creator + email
    #
    # must remain unique.
    #
    # verification_token and unsubscribe_token remain globally
    # unique.
    #
    # Batch mode is required for SQLite because we are changing
    # indexes and adding constraints to an existing table.
    # ========================================================

    with op.batch_alter_table(
        "email_subscribers",
        schema=None,
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                "creator_account_id",
                sa.Integer(),
                nullable=True,
            )
        )

        # Remove the old globally unique email index.
        batch_op.drop_index(
            "ix_email_subscribers_email"
        )

        # Re-create email as a normal lookup index.
        batch_op.create_index(
            "ix_email_subscribers_email",
            ["email"],
            unique=False,
        )

        batch_op.create_index(
            "ix_email_subscribers_creator_account_id",
            ["creator_account_id"],
            unique=False,
        )

        # Same email may subscribe to different creators,
        # but only once to the same creator.
        batch_op.create_unique_constraint(
            "uq_email_subscriber_creator_email",
            [
                "creator_account_id",
                "email",
            ],
        )

        batch_op.create_foreign_key(
            "fk_email_subscribers_creator_account_id",
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

    with op.batch_alter_table(
        "email_subscribers",
        schema=None,
    ) as batch_op:

        batch_op.drop_constraint(
            "fk_email_subscribers_creator_account_id",
            type_="foreignkey",
        )

        batch_op.drop_constraint(
            "uq_email_subscriber_creator_email",
            type_="unique",
        )

        batch_op.drop_index(
            "ix_email_subscribers_creator_account_id"
        )

        batch_op.drop_index(
            "ix_email_subscribers_email"
        )

        # Restore original globally unique email index.
        batch_op.create_index(
            "ix_email_subscribers_email",
            ["email"],
            unique=True,
        )

        batch_op.drop_column(
            "creator_account_id"
        )


    # ========================================================
    # CREATOR PROFILES
    # ========================================================

    with op.batch_alter_table(
        "creator_profiles",
        schema=None,
    ) as batch_op:

        batch_op.drop_constraint(
            "fk_creator_profiles_creator_account_id",
            type_="foreignkey",
        )

        batch_op.drop_index(
            "ix_creator_profiles_creator_account_id"
        )

        batch_op.drop_column(
            "creator_account_id"
        )


    # ========================================================
    # CONTENT POSTS
    # ========================================================

    with op.batch_alter_table(
        "content_posts",
        schema=None,
    ) as batch_op:

        batch_op.drop_constraint(
            "fk_content_posts_creator_account_id",
            type_="foreignkey",
        )

        batch_op.drop_index(
            "ix_content_posts_creator_account_id"
        )

        batch_op.drop_column(
            "creator_account_id"
        )


    # ========================================================
    # CONTENT CATEGORIES
    # ========================================================

    with op.batch_alter_table(
        "content_categories",
        schema=None,
    ) as batch_op:

        batch_op.drop_constraint(
            "fk_content_categories_creator_account_id",
            type_="foreignkey",
        )

        batch_op.drop_index(
            "ix_content_categories_creator_account_id"
        )

        batch_op.drop_column(
            "creator_account_id"
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
        "creator_accounts"
    )
