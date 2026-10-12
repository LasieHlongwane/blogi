
"""add creator white label branding and domains

Revision ID: 31636074d391
Revises: 078bb0d5d5ef
Create Date: 2026-10-08 00:51:37.161171

Reconciles pre-existing tables without dropping creator data.
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# ALEMBIC REVISION IDENTIFIERS
# ============================================================

revision = "31636074d391"
down_revision = "078bb0d5d5ef"
branch_labels = None
depends_on = None


# ============================================================
# REQUIRED COLUMNS
# ============================================================

BRANDING_COLUMNS = {
    "id",
    "creator_account_id",
    "site_title",
    "site_tagline",
    "logo_url",
    "logo_public_id",
    "favicon_url",
    "favicon_public_id",
    "cover_image_url",
    "cover_image_public_id",
    "primary_color",
    "accent_color",
    "background_color",
    "text_color",
    "theme",
    "font_family",
    "footer_text",
    "show_platform_branding",
    "created_at",
    "updated_at",
}

DOMAIN_COLUMNS = {
    "id",
    "creator_account_id",
    "hostname",
    "domain_type",
    "verification_status",
    "verification_token",
    "is_primary",
    "is_active",
    "verified_at",
    "activated_at",
    "created_at",
    "updated_at",
}


# ============================================================
# SCHEMA INSPECTION HELPERS
# ============================================================

def _inspect():
    return sa.inspect(op.get_bind())


def _table_exists(table):
    return _inspect().has_table(table)


def _validate_columns(table, expected):
    found = {
        column["name"]
        for column in _inspect().get_columns(table)
    }

    missing = sorted(expected - found)

    if missing:
        raise RuntimeError(
            f"Existing {table} is missing columns: "
            f"{', '.join(missing)}. "
            "Reconcile the schema before upgrading."
        )


def _has_unique_columns(table, columns):
    """
    Check whether the database already enforces uniqueness
    through either:

    1. A UNIQUE constraint.
    2. A UNIQUE index.

    This is important because Neon already has a separate
    UNIQUE constraint on creator_brandings.creator_account_id.
    """

    inspector = _inspect()

    for constraint in inspector.get_unique_constraints(table):
        if constraint.get("column_names") == columns:
            return True

    for index in inspector.get_indexes(table):
        if (
            index.get("column_names") == columns
            and bool(index.get("unique"))
        ):
            return True

    return False


def _ensure_index(table, name, columns, unique=False):
    """
    Ensure the requested index exists.

    An existing non-unique index is accepted for a requested
    unique index only if another UNIQUE constraint or index
    already enforces uniqueness on the same columns.

    This avoids replacing the existing Neon branding index
    unnecessarily.
    """

    inspector = _inspect()

    indexes = {
        index["name"]: index
        for index in inspector.get_indexes(table)
    }

    if name in indexes:
        existing = indexes[name]

        if existing.get("column_names") != columns:
            raise RuntimeError(
                f"Index {name} on {table} uses different columns."
            )

        existing_unique = bool(existing.get("unique"))

        if existing_unique == bool(unique):
            return

        if (
            unique
            and not existing_unique
            and _has_unique_columns(table, columns)
        ):
            # A separate UNIQUE constraint/index already
            # enforces the required rule.
            return

        raise RuntimeError(
            f"Index {name} on {table} has a different "
            "uniqueness definition and no equivalent "
            "constraint was found."
        )

    if unique and _has_unique_columns(table, columns):
        # The requested uniqueness is already enforced.
        # No additional index is required.
        return

    op.create_index(
        name,
        table,
        columns,
        unique=unique,
    )


def _validate_fk(table):
    """
    Confirm creator ownership is protected by a foreign key
    with ON DELETE CASCADE.
    """

    foreign_keys = _inspect().get_foreign_keys(table)

    for fk in foreign_keys:
        options = fk.get("options") or {}

        ondelete = str(
            options.get("ondelete") or ""
        ).upper()

        if (
            fk.get("constrained_columns")
            == ["creator_account_id"]
            and fk.get("referred_table")
            == "creator_accounts"
            and fk.get("referred_columns")
            == ["id"]
            and ondelete == "CASCADE"
        ):
            return

    raise RuntimeError(
        f"{table} requires creator_account_id -> "
        "creator_accounts.id with ON DELETE CASCADE. "
        "Reconcile the schema before upgrading."
    )


def _validate_domain_constraints():
    """
    Confirm creator domain verification tokens are unique
    and domain types are restricted to supported values.
    """

    inspector = _inspect()

    if not _has_unique_columns(
        "creator_domains",
        ["verification_token"],
    ):
        raise RuntimeError(
            "creator_domains must have a unique "
            "verification_token constraint or index."
        )

    checks = inspector.get_check_constraints(
        "creator_domains"
    )

    has_domain_type_check = any(
        "domain_type" in (check.get("sqltext") or "")
        and "subdomain" in (check.get("sqltext") or "")
        and "custom" in (check.get("sqltext") or "")
        for check in checks
    )

    if not has_domain_type_check:
        raise RuntimeError(
            "creator_domains must constrain domain_type "
            "to subdomain/custom."
        )


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    # ========================================================
    # CREATOR BRANDINGS
    # ========================================================

    if not _table_exists("creator_brandings"):

        op.create_table(
            "creator_brandings",

            sa.Column(
                "id",
                sa.Integer(),
                primary_key=True,
            ),

            sa.Column(
                "creator_account_id",
                sa.Integer(),
                nullable=False,
            ),

            sa.Column(
                "site_title",
                sa.String(180),
            ),

            sa.Column(
                "site_tagline",
                sa.String(255),
            ),

            sa.Column(
                "logo_url",
                sa.Text(),
            ),

            sa.Column(
                "logo_public_id",
                sa.String(500),
            ),

            sa.Column(
                "favicon_url",
                sa.Text(),
            ),

            sa.Column(
                "favicon_public_id",
                sa.String(500),
            ),

            sa.Column(
                "cover_image_url",
                sa.Text(),
            ),

            sa.Column(
                "cover_image_public_id",
                sa.String(500),
            ),

            sa.Column(
                "primary_color",
                sa.String(20),
                nullable=False,
            ),

            sa.Column(
                "accent_color",
                sa.String(20),
                nullable=False,
            ),

            sa.Column(
                "background_color",
                sa.String(20),
                nullable=False,
            ),

            sa.Column(
                "text_color",
                sa.String(20),
                nullable=False,
            ),

            sa.Column(
                "theme",
                sa.String(40),
                nullable=False,
            ),

            sa.Column(
                "font_family",
                sa.String(80),
                nullable=False,
            ),

            sa.Column(
                "footer_text",
                sa.String(255),
            ),

            sa.Column(
                "show_platform_branding",
                sa.Boolean(),
                nullable=False,
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
                ondelete="CASCADE",
            ),

        )

    _validate_columns(
        "creator_brandings",
        BRANDING_COLUMNS,
    )

    _validate_fk("creator_brandings")

    # Existing Neon schema:
    #
    # creator_brandings_creator_account_id_key
    #   UNIQUE (creator_account_id)
    #
    # ix_creator_brandings_creator_account_id
    #   non-unique index
    #
    # This is accepted because uniqueness is already
    # enforced by the separate UNIQUE constraint.

    _ensure_index(
        "creator_brandings",
        "ix_creator_brandings_creator_account_id",
        ["creator_account_id"],
        unique=True,
    )

    # ========================================================
    # CREATOR DOMAINS
    # ========================================================

    if not _table_exists("creator_domains"):

        op.create_table(
            "creator_domains",

            sa.Column(
                "id",
                sa.Integer(),
                primary_key=True,
            ),

            sa.Column(
                "creator_account_id",
                sa.Integer(),
                nullable=False,
            ),

            sa.Column(
                "hostname",
                sa.String(253),
                nullable=False,
            ),

            sa.Column(
                "domain_type",
                sa.String(30),
                nullable=False,
            ),

            sa.Column(
                "verification_status",
                sa.String(30),
                nullable=False,
            ),

            sa.Column(
                "verification_token",
                sa.String(255),
            ),

            sa.Column(
                "is_primary",
                sa.Boolean(),
                nullable=False,
            ),

            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
            ),

            sa.Column(
                "verified_at",
                sa.DateTime(timezone=True),
            ),

            sa.Column(
                "activated_at",
                sa.DateTime(timezone=True),
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
                "domain_type IN ('subdomain', 'custom')",
                name="ck_creator_domain_type",
            ),

            sa.ForeignKeyConstraint(
                ["creator_account_id"],
                ["creator_accounts.id"],
                ondelete="CASCADE",
            ),

            sa.UniqueConstraint(
                "verification_token",
            ),
        )

    # ========================================================
    # VALIDATE CREATOR DOMAINS
    # ========================================================

    _validate_columns(
        "creator_domains",
        DOMAIN_COLUMNS,
    )

    _validate_fk("creator_domains")

    _validate_domain_constraints()

    # ========================================================
    # CREATOR DOMAIN INDEXES
    # ========================================================

    domain_indexes = (
        (
            "ix_creator_domains_creator_account_id",
            ["creator_account_id"],
            False,
        ),
        (
            "ix_creator_domains_domain_type",
            ["domain_type"],
            False,
        ),
        (
            "ix_creator_domains_hostname",
            ["hostname"],
            True,
        ),
        (
            "ix_creator_domains_is_active",
            ["is_active"],
            False,
        ),
        (
            "ix_creator_domains_verification_status",
            ["verification_status"],
            False,
        ),
    )

    for name, columns, unique in domain_indexes:

        _ensure_index(
            "creator_domains",
            name,
            columns,
            unique=unique,
        )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():
    """
    This migration can adopt existing branding/domain tables.

    Automatically dropping those tables on downgrade could
    delete data that existed before this revision.

    Therefore, automatic downgrade is deliberately blocked.
    """

    raise RuntimeError(
        "Downgrade blocked: this migration can adopt "
        "pre-existing creator tables. "
        "Perform a reviewed, explicit schema rollback "
        "if needed."
    )
