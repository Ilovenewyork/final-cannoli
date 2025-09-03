from extensions import db
from models.team_alias import TeamAlias
from models.alert import Alert
from models.game import Game

def check_and_create_tables():
    """Check if tables exist and create them if they don't"""
    from sqlalchemy import inspect
    
    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()
    
    # Check if alerts table exists
    if 'alerts' not in existing_tables:
        print("Creating alerts table...")
        Alert.__table__.create(db.engine)
        print("Successfully created alerts table")
    else:
        print("alerts table already exists")
    
    # Check if game table exists and has relation to alerts
    if 'game' in existing_tables:
        inspector = inspect(db.engine)
        game_columns = [col['name'] for col in inspector.get_columns('game')]
        
        # Add any missing columns to game table if needed
        # (Add your column checks here if needed in the future)
        pass

def update_team_alias_table():
    # This will add the placeholder column if it doesn't exist
    from sqlalchemy import inspect
    
    inspector = inspect(db.engine)
    if 'team_alias' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('team_alias')]
        
        if 'placeholder' not in columns:
            print("Adding placeholder column to team_alias table...")
            db.session.execute('ALTER TABLE team_alias ADD COLUMN placeholder VARCHAR(10)')
            db.session.commit()
            print("Successfully added placeholder column")
        else:
            print("placeholder column already exists")
    else:
        print("team_alias table does not exist")

if __name__ == '__main__':
    from app import create_app
    app = create_app()
    with app.app_context():
        print("Checking and updating database schema...")
        check_and_create_tables()
        update_team_alias_table()
        print("Database update complete!")
