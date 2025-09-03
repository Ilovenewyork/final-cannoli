import sqlite3
import os
from app import create_app

def check_schema():
    # Get the database path from the Flask app config
    app = create_app()
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    
    if not os.path.exists(db_path):
        print(f"Database file not found at: {db_path}")
        return
    
    print(f"Checking database at: {db_path}")
    print("-" * 80)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if alerts table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alerts';")
        if not cursor.fetchone():
            print("ERROR: 'alerts' table does not exist in the database!")
            return
        
        # Get the schema of the alerts table
        print("\nAlerts table schema:")
        print("-" * 40)
        cursor.execute("PRAGMA table_info(alerts);")
        for column in cursor.fetchall():
            print(f"{column[1]}: {column[2]} {'(PK)' if column[5] > 0 else ''} {'(NOT NULL)' if not column[3] else ''}")
        
        # Check indexes
        print("\nIndexes on alerts table:")
        print("-" * 40)
        cursor.execute("PRAGMA index_list('alerts');")
        for idx in cursor.fetchall():
            idx_name = idx[1]
            cursor.execute(f"PRAGMA index_info('{idx_name}');")
            cols = [col[2] for col in cursor.fetchall()]
            print(f"- {idx_name}: {', '.join(cols)}")
        
        # Check foreign keys
        print("\nForeign keys:")
        print("-" * 40)
        cursor.execute("PRAGMA foreign_key_list('alerts');")
        fks = cursor.fetchall()
        if fks:
            for fk in fks:
                print(f"- {fk[2]} -> {fk[3]}.{fk[4]}")
        else:
            print("No foreign keys found")
        
        # Check if any data exists
        cursor.execute("SELECT COUNT(*) FROM alerts;")
        count = cursor.fetchone()[0]
        print(f"\nTotal alerts in database: {count}")
        
        if count > 0:
            print("\nLatest alerts:")
            print("-" * 40)
            cursor.execute("SELECT id, level, room, message, created_at, resolved FROM alerts ORDER BY created_at DESC LIMIT 5;")
            for alert in cursor.fetchall():
                print(f"ID: {alert[0]}, Level: {alert[1]}, Room: {alert[2]}")
                print(f"Message: {alert[3]}")
                print(f"Created: {alert[4]}, Resolved: {alert[5]}")
                print()
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    check_schema()
