import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, send_from_directory, jsonify, request
from markupsafe import Markup
from flask_wtf.csrf import CSRFProtect
from extensions import db, init_extensions, login_manager, migrate

def create_app():
    # Create the Flask application
    app = Flask(__name__)
    
    # Initialize CSRF protection
    csrf = CSRFProtect()
    
    # Configuration
    app.config.update(
        SECRET_KEY='your-secret-key-here',  # Change this to a strong secret key
        REMEMBER_COOKIE_SECURE=True,
        REMEMBER_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///quizbowl.db',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        WTF_CSRF_TIME_LIMIT=3600  # CSRF token valid for 1 hour
    )
    
    # Initialize CSRF protection
    csrf.init_app(app)
    
    # Configure logging
    if not app.debug:
        # Set up basic logging to console
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]',
            handlers=[
                logging.StreamHandler()
            ]
        )
        
        # Remove all handlers associated with the root logger
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(app.root_path, 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # Set up file handler for logging - using WatchedFileHandler for better Windows support
        log_file = os.path.join(log_dir, 'quizbowl.log')
        try:
            # Use WatchedFileHandler which handles log rotation better on Windows
            from logging.handlers import WatchedFileHandler
            file_handler = WatchedFileHandler(log_file, mode='a', encoding='utf-8')
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
            ))
            file_handler.setLevel(logging.INFO)
            
            # Configure app logger
            app.logger.addHandler(file_handler)
            app.logger.setLevel(logging.INFO)
            app.logger.info('QuizBowl application started with WatchedFileHandler')
            
        except Exception as e:
            # If file logging fails, fall back to console logging
            app.logger.error('Failed to set up file logging: %s', str(e))
            app.logger.info('Falling back to console logging only.')
    
    # Initialize CSRF protection
    csrf = CSRFProtect()
    csrf.init_app(app)
    
    # Add request logging
    @app.before_request
    def log_request_info():
        app.logger.info('Request: %s %s', request.method, request.url)
        app.logger.debug('Headers: %s', dict(request.headers))
        if request.method == 'POST':
            app.logger.info('Form data: %s', request.form)
            app.logger.debug('JSON data: %s', request.get_json(silent=True))
    
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
    
    # Initialize Flask-Migrate
    migrate.init_app(app, db)
    
    # Configure login manager
    from models.reader import Reader
    
    @login_manager.user_loader
    def load_user(user_id):
        # Try to load as Admin first, then as Reader
        from models.admin import Admin
        user = Admin.query.get(int(user_id))
        if user is None:
            user = Reader.query.get(int(user_id))
        return user
    
    # Register blueprints
    from controllers.admin_controller import admin_bp
    from controllers.public_controller import public_bp
    from controllers.reader_controller import reader_bp
    from routes.alerts import bp as alerts_bp
    from routes.protests import bp as protests_bp
    
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(reader_bp, url_prefix='/reader')
    app.register_blueprint(alerts_bp, url_prefix='/api')
    app.register_blueprint(protests_bp, url_prefix='/api')
    
    # Set the login view for the login manager
    login_manager.login_view = 'reader.login'
    
    # Simple route for the root URL
    @app.route('/')
    def index():
        return render_template('index.html')
        
    # Debug route to check URL rules
    @app.route('/debug/urls')
    def debug_urls():
        import urllib.parse
        output = []
        for rule in app.url_map.iter_rules():
            methods = ','.join(rule.methods)
            line = urllib.parse.unquote(f"{rule.endpoint}: {rule.rule} [{methods}]")
            output.append(line)
        return '<pre>' + '\n'.join(sorted(output)) + '</pre>'
    
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