"""add question progress column

Revision ID: 1234567890ab
Revises: 882307784a69
Create Date: 2025-07-18 18:42:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '1234567890ab'
down_revision = '882307784a69'
branch_labels = None
depends_on = None

def upgrade():
    # Add a new JSON column to store question progress data
    op.add_column('question', sa.Column('progress_data', sa.JSON(), nullable=True))

def downgrade():
    op.drop_column('question', 'progress_data')
