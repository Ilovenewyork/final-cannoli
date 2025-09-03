from app import create_app
from extensions import db
from sqlalchemy import inspect

def check_alerts_table():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        
        # Check if alerts table exists
        if 'alerts' not in inspector.get_table_names():
            print("ERROR: 'alerts' table does not exist in the database!")
            return
            
        # Get columns for alerts table
        columns = inspector.get_columns('alerts')
        print("\nAlerts table columns:")
        print("-" * 50)
        for col in columns:
            print(f"- {col['name']}: {col['type']} (nullable: {col['nullable']})")
        
        # Check foreign key constraints
        print("\nForeign keys:")
        print("-" * 50)
        fks = inspector.get_foreign_keys('alerts')
        for fk in fks:
            print(f"- {fk['referred_table']}.{fk['referred_columns'][0]}")
        
        # Check if any data exists
        result = db.session.execute("SELECT COUNT(*) FROM alerts")
        count = result.scalar()
        print(f"\nTotal alerts in database: {count}")

if __name__ == '__main__':
    check_alerts_table()
