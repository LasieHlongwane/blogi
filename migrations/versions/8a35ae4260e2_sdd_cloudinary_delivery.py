
"""Add Cloudinary delivery type to content media.

Revision ID: 8a35ae4260e2
Revises: 83a6913cf4a3
Create Date: 2026-10-16 02:07:50.032196

This migration:
- Adds delivery_type to content_media.
- Defaults existing media to public ('upload').
- Allows media_url to be NULL for authenticated media.
- Adds an index on delivery_type.

Existing Cloudinary assets are not automatically made private.
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION IDENTIFIERS
# ============================================================

revision = "8a35ae4260e2"
down_revision = "83a6913cf4a3"
branch_labels = None
depends_on = None


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    with op.batch_alter_table(
        "content_media",
        schema=None,
    ) as batch_op:

        # Existing media remains public until explicitly
        # migrated to authenticated Cloudinary delivery.
        batch_op.add_column(
            sa.Column(
                "delivery_type",
                sa.String(length=30),
                nullable=False,
                server_default="upload",
            )
        )

        # Authenticated media should not require a stored
        # publicly accessible URL.
        batch_op.alter_column(
            "media_url",
            existing_type=sa.Text(),
            nullable=True,
            existing_nullable=False,
        )

        batch_op.create_index(
            "ix_content_media_delivery_type",
            ["delivery_type"],
            unique=False,
        )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():

    # Downgrading requires every media_url to be non-NULL.
    # Refuse the downgrade rather than silently inventing
    # URLs or deleting protected media records.

    connection = op.get_bind()

    missing_urls = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM content_media
            WHERE media_url IS NULL
            """
        )
    ).scalar_one()

    if missing_urls:

        raise RuntimeError(
            "Cannot downgrade Cloudinary delivery migration: "
            f"{missing_urls} content_media record(s) have "
            "NULL media_url values. Restore valid media URLs "
            "or migrate these records before downgrading."
        )

    with op.batch_alter_table(
        "content_media",
        schema=None,
    ) as batch_op:

        batch_op.drop_index(
            "ix_content_media_delivery_type"
        )

        batch_op.alter_column(
            "media_url",
            existing_type=sa.Text(),
            nullable=False,
            existing_nullable=True,
        )

        batch_op.drop_column(
            "delivery_type"
        )
