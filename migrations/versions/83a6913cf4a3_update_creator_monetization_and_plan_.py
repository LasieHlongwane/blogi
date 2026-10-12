
"""Update creator monetization and plan defaults.

Revision ID: 83a6913cf4a3
Revises: 31636074d391
Create Date: 2026-10-12 04:05:31.561012

Supports SQLite and PostgreSQL.

Changes:
- New creator accounts default to the Free plan.
- Existing creator plans remain unchanged.
- Existing subscription and payment history is preserved.
- Existing unique constraints are retained.
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION IDENTIFIERS
# ============================================================

revision = "83a6913cf4a3"
down_revision = "31636074d391"
branch_labels = None
depends_on = None


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    # --------------------------------------------------------
    # UPDATE CREATOR DEFAULT PLAN
    # --------------------------------------------------------
    #
    # SQLite cannot execute:
    #
    # ALTER TABLE creator_accounts
    # ALTER COLUMN plan SET DEFAULT 'free'
    #
    # Alembic batch mode handles this by recreating the
    # table on SQLite when necessary.
    #
    # PostgreSQL supports the operation directly.
    #
    # --------------------------------------------------------

    with op.batch_alter_table(
        "creator_accounts",
        schema=None,
        recreate="auto",
    ) as batch_op:

        batch_op.alter_column(
            "plan",
            existing_type=sa.String(length=30),
            existing_nullable=False,
            server_default=sa.text("'free'"),
        )

    # --------------------------------------------------------
    # EXISTING DATA
    # --------------------------------------------------------
    #
    # No existing creator plan values are modified.
    #
    # Do not remove unique constraints from payment or
    # subscription tables.
    #
    # --------------------------------------------------------


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():

    # --------------------------------------------------------
    # RESTORE PREVIOUS DEFAULT
    # --------------------------------------------------------

    with op.batch_alter_table(
        "creator_accounts",
        schema=None,
        recreate="auto",
    ) as batch_op:

        batch_op.alter_column(
            "plan",
            existing_type=sa.String(length=30),
            existing_nullable=False,
            server_default=sa.text("'standard'"),
        )
