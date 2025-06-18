from extensions import db
from models.team_alias import TeamAlias

def update_team_alias_table():
    # This will add the placeholder column if it doesn't exist
    from sqlalchemy import inspect, Column, String
    from extensions import db
    
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('team_alias')]
    
    if 'placeholder' not in columns:
        print("Adding placeholder column to team_alias table...")
        db.session.execute('ALTER TABLE team_alias ADD COLUMN placeholder VARCHAR(10)')
        db.session.commit()
        print("Successfully added placeholder column")
    else:
        print("placeholder column already exists")

if __name__ == '__main__':
    from app import create_app
    app = create_app()
    with app.app_context():
        update_team_alias_table()
