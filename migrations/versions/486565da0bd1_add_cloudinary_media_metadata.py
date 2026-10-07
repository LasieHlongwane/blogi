"""add cloudinary media metadata

Revision ID: 486565da0bd1
Revises: 507de127591d
Create Date: 2026-10-05 01:18:33.363849

"""

from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


# ============================================================
# ALEMBIC REVISION IDENTIFIERS
# ============================================================

revision = "486565da0bd1"
down_revision = "507de127591d"
branch_labels = None
depends_on = None


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    # ========================================================
    # EMAIL DELIVERIES
    # ========================================================

    op.create_table(
        "email_deliveries",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "subscriber_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "post_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "email_type",
            sa.String(length=50),
            nullable=False,
        ),

        sa.Column(
            "recipient_email",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "subject",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["post_id"],
            ["content_posts.id"],
            ondelete="SET NULL",
        ),

        sa.ForeignKeyConstraint(
            ["subscriber_id"],
            ["email_subscribers.id"],
            ondelete="SET NULL",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),
    )


    # ========================================================
    # EMAIL DELIVERY INDEXES
    # ========================================================

    op.create_index(
        "ix_email_deliveries_email_type",
        "email_deliveries",
        ["email_type"],
        unique=False,
    )

    op.create_index(
        "ix_email_deliveries_post_id",
        "email_deliveries",
        ["post_id"],
        unique=False,
    )

    op.create_index(
        "ix_email_deliveries_recipient_email",
        "email_deliveries",
        ["recipient_email"],
        unique=False,
    )

    op.create_index(
        "ix_email_deliveries_status",
        "email_deliveries",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_email_deliveries_subscriber_id",
        "email_deliveries",
        ["subscriber_id"],
        unique=False,
    )


    # ========================================================
    # EMAIL SUBSCRIBERS
    # ========================================================
    #
    # IMPORTANT:
    #
    # We cannot immediately add updated_at as NOT NULL because
    # this table may already contain subscriber records.
    #
    # SQLite batch migration creates a temporary table and
    # copies existing rows into it. Existing rows would have
    # NULL for the newly-added column and the migration would
    # fail.
    #
    # Migration strategy:
    #
    #   1. Add updated_at as nullable.
    #   2. Backfill existing records.
    #   3. Ensure every unsubscribe_token has a value.
    #   4. Make updated_at NOT NULL.
    #   5. Make unsubscribe_token NOT NULL.
    #   6. Add unique indexes.
    #
    # This works with both SQLite and PostgreSQL.
    # ========================================================


    # --------------------------------------------------------
    # STEP 1:
    # Add updated_at temporarily as nullable.
    # --------------------------------------------------------

    with op.batch_alter_table(
        "email_subscribers",
        schema=None,
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )


    # --------------------------------------------------------
    # STEP 2:
    # Backfill updated_at.
    #
    # Prefer the existing created_at value so historical rows
    # keep a meaningful timestamp.
    #
    # If created_at were ever NULL, use current UTC time.
    # --------------------------------------------------------

    connection = op.get_bind()

    now = datetime.now(
        timezone.utc
    )

    connection.execute(
        sa.text(
            """
            UPDATE email_subscribers
            SET updated_at = COALESCE(
                created_at,
                :now
            )
            WHERE updated_at IS NULL
            """
        ),
        {
            "now": now,
        },
    )


    # --------------------------------------------------------
    # STEP 3:
    # Backfill missing unsubscribe tokens.
    #
    # unsubscribe_token is about to become NOT NULL and UNIQUE.
    #
    # Each missing token therefore needs its own unique value.
    # Do this row-by-row rather than assigning one token to all
    # missing records.
    # --------------------------------------------------------

    missing_token_rows = connection.execute(
        sa.text(
            """
            SELECT id
            FROM email_subscribers
            WHERE unsubscribe_token IS NULL
               OR TRIM(unsubscribe_token) = ''
            """
        )
    ).fetchall()


    for row in missing_token_rows:

        subscriber_id = row[0]

        unsubscribe_token = uuid.uuid4().hex

        connection.execute(
            sa.text(
                """
                UPDATE email_subscribers
                SET unsubscribe_token = :token
                WHERE id = :subscriber_id
                """
            ),
            {
                "token": unsubscribe_token,
                "subscriber_id": subscriber_id,
            },
        )


    # --------------------------------------------------------
    # STEP 4:
    # Enforce final column constraints.
    #
    # Alembic batch mode is required for SQLite because SQLite
    # cannot directly ALTER these column constraints.
    # --------------------------------------------------------

    with op.batch_alter_table(
        "email_subscribers",
        schema=None,
    ) as batch_op:

        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(
                timezone=True
            ),
            nullable=False,
        )

        batch_op.alter_column(
            "unsubscribe_token",
            existing_type=sa.String(
                length=255
            ),
            nullable=False,
        )


    # --------------------------------------------------------
    # STEP 5:
    # Create token indexes.
    # --------------------------------------------------------

    op.create_index(
        "ix_email_subscribers_unsubscribe_token",
        "email_subscribers",
        ["unsubscribe_token"],
        unique=True,
    )

    op.create_index(
        "ix_email_subscribers_verification_token",
        "email_subscribers",
        ["verification_token"],
        unique=True,
    )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():

    # ========================================================
    # EMAIL SUBSCRIBER INDEXES
    # ========================================================

    op.drop_index(
        "ix_email_subscribers_verification_token",
        table_name="email_subscribers",
    )

    op.drop_index(
        "ix_email_subscribers_unsubscribe_token",
        table_name="email_subscribers",
    )


    # ========================================================
    # EMAIL SUBSCRIBERS
    # ========================================================

    with op.batch_alter_table(
        "email_subscribers",
        schema=None,
    ) as batch_op:

        batch_op.alter_column(
            "unsubscribe_token",
            existing_type=sa.String(
                length=255
            ),
            nullable=True,
        )

        batch_op.drop_column(
            "updated_at"
        )


    # ========================================================
    # EMAIL DELIVERY INDEXES
    # ========================================================

    op.drop_index(
        "ix_email_deliveries_subscriber_id",
        table_name="email_deliveries",
    )

    op.drop_index(
        "ix_email_deliveries_status",
        table_name="email_deliveries",
    )

    op.drop_index(
        "ix_email_deliveries_recipient_email",
        table_name="email_deliveries",
    )

    op.drop_index(
        "ix_email_deliveries_post_id",
        table_name="email_deliveries",
    )

    op.drop_index(
        "ix_email_deliveries_email_type",
        table_name="email_deliveries",
    )


    # ========================================================
    # EMAIL DELIVERIES
    # ========================================================

    op.drop_table(
        "email_deliveries"
    )
