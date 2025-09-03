from app import create_app
from extensions import db
from models.admin import Admin
from werkzeug.security import generate_password_hash

def init_db():
    app = create_app()
    with app.app_context():
        # Drop all tables
        db.drop_all()
        # Create all tables
        db.create_all()
        
        # Create default admin user
        admin = Admin(username='admin')
        admin.set_password('password')  # This will set the password and handle the hash
        admin.needs_password_change = True
        db.session.add(admin)
        db.session.commit()
        
        print("Database initialized successfully!")
        print("Default admin created:")
        print(f"Username: admin")
        print(f"Password: password")
        print("\nIMPORTANT: Change the default password after first login!")

if __name__ == "__main__":
    init_db()
