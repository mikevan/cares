"""add default_report_year to users

Revision ID: 20260109_add_default_report_year
Revises: None
Create Date: 2026-01-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260109_add_default_report_year'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add nullable integer column to users
    op.add_column('users', sa.Column('default_report_year', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('users', 'default_report_year')
