import os
import sys
from flask import Flask, render_template, send_from_directory, jsonify
from markupsafe import Markup
from extensions import db, init_extensions, login_manager

def create_app():
    # Create the Flask application
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change this to a strong secret key
    
    def escapejs(value):
        """Escape a string for use in JavaScript strings."""
        if value is None:
            return ''
        value = str(value)
        escape_map = {
            '\\': '\\\\u005C',
            "'": '\\\\u0027',
            '"': '\\\\u0022',
            '>': '\\\\u003E',
            '<': '\\\\u003C',
            '&': '\\\\u0026',
            '=': '\\\\u003D',
            '-': '\\\\u002D',
            ';': '\\\\u003B',
            '\\u2028': '\\\\u2028',
            '\\u2029': '\\\\u2029'
        }
        for k, v in escape_map.items():
            value = value.replace(k, v)
        return Markup(value)
    
    # Add the escapejs filter to Jinja2
    app.jinja_env.filters['escapejs'] = escapejs
    
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quizbowl.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')
    
    # Disable template caching in development
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True
    
    # Ensure the upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize extensions
    init_extensions(app)
    
    
    # Import and register blueprints after app and db are initialized
    try:
        print("\n=== Registering Blueprints ===")
        from controllers import admin_controller
        from controllers.public_controller import public_bp
        from controllers.reader_controller import reader_bp
        
        print("Registering admin_blueprint...")
        app.register_blueprint(admin_controller.admin_bp, url_prefix='/admin')
        print("Registering public_blueprint...")
        app.register_blueprint(public_bp, url_prefix='/')
        print("Registering reader_blueprint...")
        app.register_blueprint(reader_bp, url_prefix='/reader')
        print("=== Blueprints Registered ===\n")
        
        
    except Exception as e:
        print(f"Error registering blueprints: {e}", file=sys.stderr)
    
    # Simple route for the root URL
    @app.route('/')
    def index():
        return render_template('index.html')
    
    # Route to serve uploaded files
    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('500.html'), 500
    
    return app

# Create the Flask application
app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    try:
        app.run(debug=True, use_reloader=True, use_debugger=True, use_evalex=True, host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"Error starting the application: {e}", file=sys.stderr)
        sys.exit(1)