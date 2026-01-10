<%import os, re, sys
%>
"""
Auto-generated Alembic migration script.
"""

def render_imports():
    return 'from alembic import op\nimport sqlalchemy as sa\n'
%>
${render_imports()}

# revision identifiers, used by Alembic.
revision = '${up_revision}'
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


def upgrade():
${upgrades|indent(4)}


def downgrade():
${downgrades|indent(4)}
