"""add creator monetisation models

Revision ID: 078bb0d5d5ef
Revises: 47b9231e5dea
Create Date: 2026-10-08 00:12:13.232778

Reconciles a pre-existing payout table without dropping its data.
Review schema differences before using on production.
"""

from alembic import op
import sqlalchemy as sa

revision = "078bb0d5d5ef"
down_revision = "47b9231e5dea"
branch_labels = None
depends_on = None


def _table_exists(name):
    return sa.inspect(op.get_bind()).has_table(name)


def _index_exists(table, name):
    return any(idx["name"] == name for idx in sa.inspect(op.get_bind()).get_indexes(table))


def _unique_exists(table, name):
    inspector = sa.inspect(op.get_bind())
    return any(c["name"] == name for c in inspector.get_unique_constraints(table))


def _require_columns(table, names):
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    missing = set(names) - existing
    if missing:
        raise RuntimeError(f"Existing {table} is missing columns: {sorted(missing)}. Reconcile schema before upgrading.")


def _create_index_if_missing(name, table, columns, unique=False):
    if not _index_exists(table, name):
        op.create_index(name, table, columns, unique=unique)


def _assert_unique_single_column(table, column):
    """Require an existing single-column uniqueness guarantee, or create one separately."""
    inspector = sa.inspect(op.get_bind())
    for item in inspector.get_unique_constraints(table):
        if item.get("column_names") == [column]:
            return True
    for item in inspector.get_indexes(table):
        if item.get("unique") and item.get("column_names") == [column]:
            return True
    return False


def _ensure_payout_foreign_key():
    inspector = sa.inspect(op.get_bind())
    for fk in inspector.get_foreign_keys("creator_payout_accounts"):
        if (fk.get("constrained_columns") == ["creator_account_id"]
                and fk.get("referred_table") == "creator_accounts"
                and fk.get("referred_columns") == ["id"]):
            if (fk.get("options") or {}).get("ondelete", "").upper() != "CASCADE":
                raise RuntimeError("Existing creator_payout_accounts foreign key does not use ON DELETE CASCADE")
            return
    raise RuntimeError("Existing creator_payout_accounts has no expected creator_account_id foreign key")


def upgrade():
    # Existing payout records must be preserved. Only create this table if absent.
    if not _table_exists("creator_payout_accounts"):
        op.create_table(
            "creator_payout_accounts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("creator_account_id", sa.Integer(), nullable=False),
            sa.Column("provider", sa.String(length=30), nullable=False),
            sa.Column("provider_subaccount_code", sa.String(length=255), nullable=True),
            sa.Column("business_name", sa.String(length=180), nullable=True),
            sa.Column("account_name", sa.String(length=180), nullable=True),
            sa.Column("settlement_bank", sa.String(length=180), nullable=True),
            sa.Column("account_number_last4", sa.String(length=4), nullable=True),
            sa.Column("percentage_charge", sa.Numeric(precision=5, scale=2), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["creator_account_id"], ["creator_accounts.id"],
                name="fk_creator_payout_accounts_creator_account_id", ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        _require_columns("creator_payout_accounts", [
            "id", "creator_account_id", "provider", "provider_subaccount_code",
            "business_name", "account_name", "settlement_bank", "account_number_last4",
            "percentage_charge", "status", "connected_at", "disabled_at",
            "created_at", "updated_at",
        ])
        _ensure_payout_foreign_key()

    _create_index_if_missing("ix_creator_payout_accounts_creator_account_id", "creator_payout_accounts", ["creator_account_id"], unique=True)
    _create_index_if_missing("ix_creator_payout_accounts_provider", "creator_payout_accounts", ["provider"])
    _create_index_if_missing("ix_creator_payout_accounts_provider_subaccount_code", "creator_payout_accounts", ["provider_subaccount_code"], unique=True)
    _create_index_if_missing("ix_creator_payout_accounts_status", "creator_payout_accounts", ["status"])

    # Fundraising campaigns: leave existing data in place, but require a full
    # schema review if this table has already been created outside Alembic.
    if _table_exists("fundraising_campaigns"):
        raise RuntimeError("fundraising_campaigns already exists; inspect its schema before replaying this migration")
    op.create_table(
        "fundraising_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("creator_account_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cover_image_url", sa.Text(), nullable=True),
        sa.Column("cover_image_public_id", sa.String(length=500), nullable=True),
        sa.Column("goal_amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("goal_amount_cents > 0", name="ck_fundraising_campaign_positive_goal"),
        sa.ForeignKeyConstraint(["creator_account_id"], ["creator_accounts.id"], name="fk_fundraising_campaigns_creator_account_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("creator_account_id", "slug", name="uq_fundraising_campaign_creator_slug"),
    )
    for name, columns in [
        ("ix_fundraising_campaigns_creator_account_id", ["creator_account_id"]),
        ("ix_fundraising_campaigns_ends_at", ["ends_at"]),
        ("ix_fundraising_campaigns_published_at", ["published_at"]),
        ("ix_fundraising_campaigns_slug", ["slug"]),
        ("ix_fundraising_campaigns_starts_at", ["starts_at"]),
        ("ix_fundraising_campaigns_status", ["status"]),
    ]:
        op.create_index(name, "fundraising_campaigns", columns, unique=False)

    if _table_exists("fan_payments"):
        raise RuntimeError("fan_payments already exists; inspect its schema before replaying this migration")
    op.create_table(
        "fan_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("creator_account_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column("payment_type", sa.String(length=30), nullable=False),
        sa.Column("supporter_name", sa.String(length=120), nullable=True),
        sa.Column("supporter_email", sa.String(length=255), nullable=True),
        sa.Column("supporter_message", sa.String(length=500), nullable=True),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("platform_fee_cents", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("provider_transaction_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="ck_fan_payment_positive_amount"),
        sa.CheckConstraint("platform_fee_cents >= 0", name="ck_fan_payment_nonnegative_platform_fee"),
        sa.ForeignKeyConstraint(["campaign_id"], ["fundraising_campaigns.id"], name="fk_fan_payments_campaign_id", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["creator_account_id"], ["creator_accounts.id"], name="fk_fan_payments_creator_account_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns, unique in [
        ("ix_fan_payments_campaign_id", ["campaign_id"], False),
        ("ix_fan_payments_created_at", ["created_at"], False),
        ("ix_fan_payments_creator_account_id", ["creator_account_id"], False),
        ("ix_fan_payments_paid_at", ["paid_at"], False),
        ("ix_fan_payments_payment_type", ["payment_type"], False),
        ("ix_fan_payments_provider", ["provider"], False),
        ("ix_fan_payments_provider_reference", ["provider_reference"], True),
        ("ix_fan_payments_provider_transaction_id", ["provider_transaction_id"], True),
        ("ix_fan_payments_status", ["status"], False),
        ("ix_fan_payments_supporter_email", ["supporter_email"], False),
    ]:
        op.create_index(name, "fan_payments", columns, unique=unique)

    # Tenant-scoped slugs. An already non-unique slug index is okay, but the
    # expected per-creator unique constraint must be present or added.
    for table, unique_name in [
        ("content_categories", "uq_content_category_creator_slug"),
        ("content_posts", "uq_content_post_creator_slug"),
    ]:
        inspector = sa.inspect(op.get_bind())
        indexes = {item["name"]: item for item in inspector.get_indexes(table)}
        slug_index = indexes.get(f"ix_{table}_slug")
        if slug_index is not None and slug_index.get("unique"):
            op.drop_index(f"ix_{table}_slug", table_name=table)
            slug_index = None
        if slug_index is None:
            op.create_index(f"ix_{table}_slug", table, ["slug"], unique=False)
        if not _unique_exists(table, unique_name):
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.create_unique_constraint(unique_name, ["creator_account_id", "slug"])

    _create_index_if_missing("ix_creator_accounts_plan", "creator_accounts", ["plan"])


def downgrade():
    """Intentionally blocked: this revision may adopt pre-existing user data.

    Automatically dropping a table that this migration did not create could
    delete creator payout records. A deliberate audited rollback is required.
    """
    raise RuntimeError(
        "Downgrade blocked for reconciled monetisation migration: "
        "back up data and prepare a reviewed manual rollback."
    )
