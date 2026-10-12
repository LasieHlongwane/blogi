"""add creator white label branding and domains

Revision ID: 31636074d391
Revises: 078bb0d5d5ef
Create Date: 2026-10-08 00:51:37.161171

Reconciles pre-existing tables without dropping creator data.
"""
from alembic import op
import sqlalchemy as sa

revision = '31636074d391'
down_revision = '078bb0d5d5ef'
branch_labels = None
depends_on = None

BRANDING_COLUMNS = {
    'id', 'creator_account_id', 'site_title', 'site_tagline',
    'logo_url', 'logo_public_id', 'favicon_url', 'favicon_public_id',
    'cover_image_url', 'cover_image_public_id', 'primary_color',
    'accent_color', 'background_color', 'text_color', 'theme',
    'font_family', 'footer_text', 'show_platform_branding',
    'created_at', 'updated_at',
}
DOMAIN_COLUMNS = {
    'id', 'creator_account_id', 'hostname', 'domain_type',
    'verification_status', 'verification_token', 'is_primary',
    'is_active', 'verified_at', 'activated_at', 'created_at', 'updated_at',
}


def _inspect():
    return sa.inspect(op.get_bind())


def _table_exists(table):
    return _inspect().has_table(table)


def _validate_columns(table, expected):
    found = {c['name'] for c in _inspect().get_columns(table)}
    missing = sorted(expected - found)
    if missing:
        raise RuntimeError(
            f"Existing {table} is missing columns: {', '.join(missing)}. "
            "Reconcile the schema before upgrading."
        )


def _ensure_index(table, name, columns, unique=False):
    inspector = _inspect()
    indexes = {i['name']: i for i in inspector.get_indexes(table)}
    if name in indexes:
        existing = indexes[name]
        if (existing.get('column_names') != columns or
                bool(existing.get('unique')) != bool(unique)):
            raise RuntimeError(f"Index {name} on {table} has a different definition")
        return
    # A different-named unique constraint may already enforce the rule;
    # this named index is still created for consistency with the models.
    op.create_index(name, table, columns, unique=unique)


def _validate_fk(table):
    fks = _inspect().get_foreign_keys(table)
    if not any(
        fk.get('constrained_columns') == ['creator_account_id']
        and fk.get('referred_table') == 'creator_accounts'
        and fk.get('referred_columns') == ['id']
        and (fk.get('options') or {}).get('ondelete', '').upper() == 'CASCADE'
        for fk in fks
    ):
        raise RuntimeError(
            f"{table} requires creator_account_id -> creator_accounts.id "
            "with ON DELETE CASCADE; reconcile before upgrading"
        )


def _validate_domain_constraints():
    inspector = _inspect()
    uniques = inspector.get_unique_constraints('creator_domains')
    indexes = inspector.get_indexes('creator_domains')
    if not any(u.get('column_names') == ['verification_token'] for u in uniques) and not any(
        i.get('column_names') == ['verification_token'] and i.get('unique') for i in indexes
    ):
        raise RuntimeError('creator_domains must have unique verification_token')
    checks = inspector.get_check_constraints('creator_domains')
    if not any('domain_type' in (c.get('sqltext') or '') and
               'subdomain' in (c.get('sqltext') or '') and
               'custom' in (c.get('sqltext') or '') for c in checks):
        raise RuntimeError('creator_domains must constrain domain_type to subdomain/custom')


def upgrade():
    if not _table_exists('creator_brandings'):
        op.create_table(
            'creator_brandings',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('creator_account_id', sa.Integer(), nullable=False),
            sa.Column('site_title', sa.String(180)),
            sa.Column('site_tagline', sa.String(255)),
            sa.Column('logo_url', sa.Text()),
            sa.Column('logo_public_id', sa.String(500)),
            sa.Column('favicon_url', sa.Text()),
            sa.Column('favicon_public_id', sa.String(500)),
            sa.Column('cover_image_url', sa.Text()),
            sa.Column('cover_image_public_id', sa.String(500)),
            sa.Column('primary_color', sa.String(20), nullable=False),
            sa.Column('accent_color', sa.String(20), nullable=False),
            sa.Column('background_color', sa.String(20), nullable=False),
            sa.Column('text_color', sa.String(20), nullable=False),
            sa.Column('theme', sa.String(40), nullable=False),
            sa.Column('font_family', sa.String(80), nullable=False),
            sa.Column('footer_text', sa.String(255)),
            sa.Column('show_platform_branding', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['creator_account_id'], ['creator_accounts.id'], ondelete='CASCADE'),
        )
    _validate_columns('creator_brandings', BRANDING_COLUMNS)
    _validate_fk('creator_brandings')
    _ensure_index('creator_brandings', 'ix_creator_brandings_creator_account_id', ['creator_account_id'], unique=True)

    if not _table_exists('creator_domains'):
        op.create_table(
            'creator_domains',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('creator_account_id', sa.Integer(), nullable=False),
            sa.Column('hostname', sa.String(253), nullable=False),
            sa.Column('domain_type', sa.String(30), nullable=False),
            sa.Column('verification_status', sa.String(30), nullable=False),
            sa.Column('verification_token', sa.String(255)),
            sa.Column('is_primary', sa.Boolean(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('verified_at', sa.DateTime(timezone=True)),
            sa.Column('activated_at', sa.DateTime(timezone=True)),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("domain_type IN ('subdomain', 'custom')", name='ck_creator_domain_type'),
            sa.ForeignKeyConstraint(['creator_account_id'], ['creator_accounts.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('verification_token'),
        )
    _validate_columns('creator_domains', DOMAIN_COLUMNS)
    _validate_fk('creator_domains')
    _validate_domain_constraints()
    for name, cols, unique in (
        ('ix_creator_domains_creator_account_id', ['creator_account_id'], False),
        ('ix_creator_domains_domain_type', ['domain_type'], False),
        ('ix_creator_domains_hostname', ['hostname'], True),
        ('ix_creator_domains_is_active', ['is_active'], False),
        ('ix_creator_domains_verification_status', ['verification_status'], False),
    ):
        _ensure_index('creator_domains', name, cols, unique)


def downgrade():
    # This revision may have adopted pre-existing tables. Their provenance
    # cannot be recovered on downgrade, so fail safely instead of deleting
    # creator branding/domain data or configuration.
    raise RuntimeError(
        'Downgrade blocked: this migration can adopt pre-existing creator tables. '
        'Perform a reviewed, explicit schema rollback if needed.'
    )
