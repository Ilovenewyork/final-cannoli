"""
This script migrates the database to use tournament_id instead of tournament_name
for the Game and TeamAlias models.
"""
import sys
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the app to get the database configuration
from app import create_app

# Create the Flask app and push the application context
app = create_app()
app.app_context().push()

# Get the database URI from the app config
DATABASE_URI = app.config['SQLALCHEMY_DATABASE_URI']

def run_migration():
    print("Starting migration...")
    
    # Create an engine and session
    engine = create_engine(DATABASE_URI)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Start a transaction
        with session.begin():
            print("1. Adding tournament_id columns...")
            
            # Add tournament_id columns if they don't exist
            try:
                # For SQLite
                session.execute(text("""
                    PRAGMA foreign_keys=off;
                    
                    -- Create new tables with the updated schema
                    CREATE TABLE IF NOT EXISTS game_new (
                        id INTEGER NOT NULL,
                        team1 VARCHAR(100),
                        team2 VARCHAR(100),
                        result INTEGER,
                        tournament_id INTEGER,
                        round_number INTEGER,
                        stage_id INTEGER,
                        scorecard TEXT,
                        PRIMARY KEY (id),
                        FOREIGN KEY(tournament_id) REFERENCES tournament (id)
                    );
                    
                    CREATE TABLE IF NOT EXISTS team_alias_new (
                        id INTEGER NOT NULL,
                        team_id VARCHAR(100) NOT NULL,
                        team_name VARCHAR(100) NOT NULL,
                        tournament_id INTEGER,
                        stage_id INTEGER,
                        PRIMARY KEY (id),
                        FOREIGN KEY(tournament_id) REFERENCES tournament (id)
                    );
                    
                    -- Copy data from old tables to new tables
                    INSERT INTO game_new (id, team1, team2, result, round_number, stage_id, scorecard, tournament_id)
                    SELECT g.id, g.team1, g.team2, g.result, g.round_number, g.stage_id, g.scorecard, t.id
                    FROM game g
                    JOIN tournament t ON g.tournament_name = t.name;
                    
                    INSERT INTO team_alias_new (id, team_id, team_name, tournament_id, stage_id)
                    SELECT ta.id, ta.team_id, ta.team_name, t.id, ta.stage_id
                    FROM team_alias ta
                    JOIN tournament t ON ta.tournament_name = t.name;
                    
                    -- Drop old tables
                    DROP TABLE game;
                    DROP TABLE team_alias;
                    
                    -- Rename new tables
                    ALTER TABLE game_new RENAME TO game;
                    ALTER TABLE team_alias_new RENAME TO team_alias;
                    
                    -- Recreate indexes
                    CREATE INDEX ix_game_tournament_id ON game (tournament_id);
                    CREATE INDEX ix_team_alias_tournament_id ON team_alias (tournament_id);
                    
                    PRAGMA foreign_keys=on;
                
                """))
                
                print("Migration completed successfully!")
                
            except Exception as e:
                print(f"Error during migration: {str(e)}")
                session.rollback()
                raise
            
    except Exception as e:
        print(f"Error: {str(e)}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    print("Starting tournament reference migration...")
    run_migration()
    print("Migration completed!")
