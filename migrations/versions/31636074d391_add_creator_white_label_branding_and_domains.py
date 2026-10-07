"""add creator white label branding and domains

Revision ID: 31636074d391
Revises: 078bb0d5d5ef
Create Date: 2026-10-08 00:51:37.161171

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '31636074d391'
down_revision = '078bb0d5d5ef'
branch_labels = None
depends_on = None


def upgrade():
    # White-label tables only. Existing subscriptions and payment
    # uniqueness constraints must remain intact.
    op.create_table(
        'creator_brandings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('creator_account_id', sa.Integer(), nullable=False),
        sa.Column('site_title', sa.String(length=180), nullable=True),
        sa.Column('site_tagline', sa.String(length=255), nullable=True),
        sa.Column('logo_url', sa.Text(), nullable=True),
        sa.Column('logo_public_id', sa.String(length=500), nullable=True),
        sa.Column('favicon_url', sa.Text(), nullable=True),
        sa.Column('favicon_public_id', sa.String(length=500), nullable=True),
        sa.Column('cover_image_url', sa.Text(), nullable=True),
        sa.Column('cover_image_public_id', sa.String(length=500), nullable=True),
        sa.Column('primary_color', sa.String(length=20), nullable=False),
        sa.Column('accent_color', sa.String(length=20), nullable=False),
        sa.Column('background_color', sa.String(length=20), nullable=False),
        sa.Column('text_color', sa.String(length=20), nullable=False),
        sa.Column('theme', sa.String(length=40), nullable=False),
        sa.Column('font_family', sa.String(length=80), nullable=False),
        sa.Column('footer_text', sa.String(length=255), nullable=True),
        sa.Column('show_platform_branding', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['creator_account_id'], ['creator_accounts.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('creator_brandings', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_creator_brandings_creator_account_id'),
            ['creator_account_id'], unique=True,
        )

    op.create_table(
        'creator_domains',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('creator_account_id', sa.Integer(), nullable=False),
        sa.Column('hostname', sa.String(length=253), nullable=False),
        sa.Column('domain_type', sa.String(length=30), nullable=False),
        sa.Column('verification_status', sa.String(length=30), nullable=False),
        sa.Column('verification_token', sa.String(length=255), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "domain_type IN ('subdomain', 'custom')",
            name='ck_creator_domain_type',
        ),
        sa.ForeignKeyConstraint(
            ['creator_account_id'], ['creator_accounts.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('verification_token'),
    )
    with op.batch_alter_table('creator_domains', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_creator_domains_creator_account_id'),
            ['creator_account_id'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_creator_domains_domain_type'),
            ['domain_type'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_creator_domains_hostname'),
            ['hostname'], unique=True,
        )
        batch_op.create_index(
            batch_op.f('ix_creator_domains_is_active'),
            ['is_active'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_creator_domains_verification_status'),
            ['verification_status'], unique=False,
        )


def downgrade():
    # Revert only the white-label additions.
    with op.batch_alter_table('creator_domains', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_creator_domains_verification_status'))
        batch_op.drop_index(batch_op.f('ix_creator_domains_is_active'))
        batch_op.drop_index(batch_op.f('ix_creator_domains_hostname'))
        batch_op.drop_index(batch_op.f('ix_creator_domains_domain_type'))
        batch_op.drop_index(batch_op.f('ix_creator_domains_creator_account_id'))
    op.drop_table('creator_domains')

    with op.batch_alter_table('creator_brandings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_creator_brandings_creator_account_id'))
    op.drop_table('creator_brandings')
