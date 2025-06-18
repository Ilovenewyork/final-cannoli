"""update tournament references

Revision ID: 123456789abc
Revises: <previous_migration_id>
Create Date: 2025-06-18 14:03:04.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '123456789abc'
down_revision = '<previous_migration_id>'
branch_labels = None
depends_on = None

def upgrade():
    # Add new columns
    op.add_column('game', sa.Column('tournament_id', sa.Integer(), nullable=True))
    op.add_column('team_alias', sa.Column('tournament_id', sa.Integer(), nullable=True))
    
    # Create foreign key constraints
    op.create_foreign_key('fk_game_tournament', 'game', 'tournament', ['tournament_id'], ['id'])
    op.create_foreign_key('fk_team_alias_tournament', 'team_alias', 'tournament', ['tournament_id'], ['id'])
    
    # Migrate data from tournament_name to tournament_id
    connection = op.get_bind()
    
    # Update game table
    connection.execute("""
        UPDATE game g
        JOIN tournament t ON g.tournament_name = t.name
        SET g.tournament_id = t.id
    """)
    
    # Update team_alias table
    connection.execute("""
        UPDATE team_alias ta
        JOIN tournament t ON ta.tournament_name = t.name
        SET ta.tournament_id = t.id
    """)
    
    # Make the new columns non-nullable after data migration
    op.alter_column('game', 'tournament_id', nullable=False)
    op.alter_column('team_alias', 'tournament_id', nullable=False)
    
    # Drop the old columns
    op.drop_constraint('fk_game_tournament_name', 'game', type_='foreignkey')
    op.drop_column('game', 'tournament_name')
    op.drop_constraint('fk_team_alias_tournament_name', 'team_alias', type_='foreignkey')
    op.drop_column('team_alias', 'tournament_name')
    
    # Drop the old indexes
    op.drop_index(op.f('ix_game_tournament_name'), table_name='game')
    op.drop_index(op.f('ix_team_alias_tournament_name'), table_name='team_alias')

def downgrade():
    # Add back the old columns
    op.add_column('team_alias', sa.Column('tournament_name', mysql.VARCHAR(length=100), nullable=True))
    op.add_column('game', sa.Column('tournament_name', mysql.VARCHAR(length=100), nullable=True))
    
    # Create old indexes
    op.create_index(op.f('ix_team_alias_tournament_name'), 'team_alias', ['tournament_name'], unique=False)
    op.create_index(op.f('ix_game_tournament_name'), 'game', ['tournament_name'], unique=False)
    
    # Migrate data back from tournament_id to tournament_name
    connection = op.get_bind()
    
    # Update game table
    connection.execute("""
        UPDATE game g
        JOIN tournament t ON g.tournament_id = t.id
        SET g.tournament_name = t.name
    """)
    
    # Update team_alias table
    connection.execute("""
        UPDATE team_alias ta
        JOIN tournament t ON ta.tournament_id = t.id
        SET ta.tournament_name = t.name
    """)
    
    # Make the old columns non-nullable
    op.alter_column('game', 'tournament_name', nullable=False)
    op.alter_column('team_alias', 'tournament_name', nullable=False)
    
    # Recreate old foreign key constraints
    op.create_foreign_key('fk_game_tournament_name', 'game', 'tournament', ['tournament_name'], ['name'])
    op.create_foreign_key('fk_team_alias_tournament_name', 'team_alias', 'tournament', ['tournament_name'], ['name'])
    
    # Drop the new columns
    op.drop_constraint('fk_game_tournament', 'game', type_='foreignkey')
    op.drop_column('game', 'tournament_id')
    op.drop_constraint('fk_team_alias_tournament', 'team_alias', type_='foreignkey')
    op.drop_column('team_alias', 'tournament_id')
