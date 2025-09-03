import os
import sqlite3

def check_database():
    # Path to the database file (adjust if needed)
    db_path = 'instance/quizbowl.db'
    
    if not os.path.exists(db_path):
        print(f"ERROR: Database file not found at {db_path}")
        print("Please make sure the Flask application has been run at least once to create the database.")
        return
    
    print(f"Checking database at: {os.path.abspath(db_path)}")
    print("-" * 60)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # List all tables
        print("\nTables in database:")
        print("-" * 30)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        for table in tables:
            print(f"- {table[0]}")
        
        # Check if alerts table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alerts';")
        if not cursor.fetchone():
            print("\nERROR: 'alerts' table does not exist in the database!")
            print("You need to run database migrations to create the alerts table.")
            print("Run these commands in the terminal:")
            print("1. flask db migrate -m 'add alerts table'")
            print("2. flask db upgrade")
            return
        
        # Get alerts table structure
        print("\nAlerts table structure:")
        print("-" * 30)
        cursor.execute("PRAGMA table_info(alerts);")
        columns = cursor.fetchall()
        for col in columns:
            print(f"- {col[1]}: {col[2]} {'(PK)' if col[5] > 0 else ''} {'NOT NULL' if not col[3] else ''}")
        
        # Check for any data in alerts table
        cursor.execute("SELECT COUNT(*) FROM alerts;")
        count = cursor.fetchone()[0]
        print(f"\nTotal alerts in database: {count}")
        
        if count > 0:
            print("\nRecent alerts:")
            print("-" * 30)
            cursor.execute("SELECT id, level, room, message, created_at, resolved FROM alerts ORDER BY created_at DESC LIMIT 5;")
            for alert in cursor.fetchall():
                print(f"ID: {alert[0]}, Level: {alert[1]}, Room: {alert[2]}")
                print(f"Message: {alert[3]}")
                print(f"Created: {alert[4]}, Resolved: {alert[5]}")
                print()
        
    except sqlite3.Error as e:
        print(f"\nDatabase error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    check_database()
