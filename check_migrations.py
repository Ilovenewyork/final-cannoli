import os
from app import create_app
from extensions import db, migrate

def check_migrations():
    app = create_app()
    
    with app.app_context():
        # Get database path
        db_uri = app.config['SQLALCHEMY_DATABASE_URI']
        db_path = db_uri.replace('sqlite:///', '')
        print(f"Database path: {db_path}")
        print(f"Database exists: {os.path.exists(db_path)}")
        
        # Check migrations directory
        migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
        print(f"Migrations directory: {migrations_dir}")
        print(f"Migrations directory exists: {os.path.exists(migrations_dir)}")
        
        if os.path.exists(migrations_dir):
            print("\nMigration versions:")
            versions_dir = os.path.join(migrations_dir, 'versions')
            if os.path.exists(versions_dir):
                for f in os.listdir(versions_dir):
                    if f.endswith('.py'):
                        print(f"- {f}")
        
        # Check if tables exist
        print("\nChecking tables in database:")
        tables = db.engine.table_names()
        for table in tables:
            print(f"- {table}")
        
        # Check if alerts table exists
        if 'alerts' not in tables:
            print("\nERROR: 'alerts' table does not exist in the database!")
            print("You may need to run database migrations.")
            print("Try running these commands:")
            print("1. flask db migrate -m 'add alerts table'")
            print("2. flask db upgrade")
        else:
            print("\nAlerts table exists. Checking columns...")
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            columns = inspector.get_columns('alerts')
            for col in columns:
                print(f"- {col['name']}: {col['type']} (nullable: {col['nullable']})")

if __name__ == '__main__':
    check_migrations()
