from app import create_app
from extensions import db

def list_tables():
    """List all tables in the database"""
    from sqlalchemy import inspect
    
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print("\nDatabase Tables:")
        print("-" * 50)
        for table in tables:
            print(f"- {table}")
            
            # List columns for each table
            columns = inspector.get_columns(table)
            for column in columns:
                print(f"  - {column['name']} ({column['type']})")
            print()

if __name__ == '__main__':
    list_tables()
