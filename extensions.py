from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy import MetaData

# Create SQLAlchemy instance with explicit metadata
metadata = MetaData()
db = SQLAlchemy(metadata=metadata)

# Create login manager
login_manager = LoginManager()
login_manager.login_view = 'admin.login'

# Create migration manager
migrate = Migrate()

@login_manager.user_loader
def load_user(user_id):
    # Import inside function to avoid circular imports
    from models.admin import Admin
    return Admin.query.get(int(user_id))

def init_extensions(app):
    """Initialize Flask extensions with the given app."""
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    
    with app.app_context():
        # Import models inside app context to avoid circular imports
        from models import tournament, game, admin, question, team_alias, player
        
        # Create tables if they don't exist
        db.create_all()
        
        # Create default admin user if it doesn't exist
        from models.admin import Admin
        if not Admin.query.filter_by(username='admin').first():
            admin_user = Admin(username='admin')
            admin_user.set_password('admin')
            db.session.add(admin_user)
            try:
                db.session.commit()
                print("Created default admin user")
            except Exception as e:
                db.session.rollback()
                print(f"Error creating default admin: {e}")
