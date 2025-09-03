"""merge multiple heads

Revision ID: d16507872903
Revises: 4a5ce75214ed, update_protest_model
Create Date: 2025-07-28 10:33:19.578099

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd16507872903'
down_revision = ('4a5ce75214ed', 'update_protest_model')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
