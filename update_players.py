from extensions import db
from models.player import Player
from models.team_alias import TeamAlias

def update_players_table():
    # Add team_id column if it doesn't exist
    from sqlalchemy import inspect
    
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('player')]
    
    if 'team_id' not in columns:
        print("Adding team_id column to player table...")
        try:
            # Add the new column
            db.session.execute('ALTER TABLE player ADD COLUMN team_id VARCHAR(10)')
            
            # Update existing records to set team_id based on their current alias
            players = Player.query.all()
            for player in players:
                if player.alias_rel:
                    player.team_id = player.alias_rel.team_id
            
            # Make the column non-nullable after populating it
            db.session.execute('UPDATE player SET team_id = alias_id WHERE team_id IS NULL')
            db.session.execute('ALTER TABLE player ALTER COLUMN team_id SET NOT NULL')
            
            db.session.commit()
            print("Successfully updated player table with team_id")
        except Exception as e:
            db.session.rollback()
            print(f"Error updating player table: {e}")
            raise
    else:
        print("team_id column already exists")

if __name__ == '__main__':
    from app import create_app
    app = create_app()
    with app.app_context():
        update_players_table()
