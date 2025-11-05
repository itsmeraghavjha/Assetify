import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_mail import Mail
from flask_migrate import Migrate
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler

# Load .env file
load_dotenv(os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), '.env'))

# --- Initialize Extensions (Globally) ---
# We define them here, but initialize them in the create_app function
db = SQLAlchemy()
mail = Mail()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'  # Blueprint name + function name
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


def create_app():
    """
    The App Factory.
    """
    app = Flask(__name__,
                template_folder='../templates',  # Tell Flask where to find templates
                static_folder='../static')     # Tell Flask where to find static files

    basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

    # --- CONFIG ---
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set. Did you forget to set up your .env file?")
    
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['ITEMS_PER_PAGE'] = 20
    app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
    app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Mail Config
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', '1', 't']
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        print("="*50)
        print("WARNING: Email credentials not set in .env")
        print("Email functionality will be disabled.")
        print("="*50)

    # --- Initialize Extensions with the App ---
    db.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # --- Import Models & User Loader ---
    # We must import models *after* db is defined
    from models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login"""
        try:
            return db.session.get(User, int(user_id))
        except (ValueError, TypeError):
            return None

    # --- Register Blueprints ---
    with app.app_context():
        from .auth_routes import auth_bp
        from .core_routes import core_bp
        from .admin_routes import admin_bp

        app.register_blueprint(auth_bp, url_prefix='/')
        app.register_blueprint(core_bp, url_prefix='/')
        app.register_blueprint(admin_bp, url_prefix='/admin')

        # --- Register Error Handlers & Context Processor ---
        @app.context_processor
        def inject_global_vars():
            """Make variables available in all templates"""
            return dict(current_user=current_user)

        @app.errorhandler(404)
        def not_found_error(error):
            """Handle 404 errors"""
            return render_template('404.html'), 404

        @app.errorhandler(500)
        def internal_error(error):
            """Handle 500 errors"""
            db.session.rollback()
            return render_template('500.html'), 500

        # --- Configure Logging ---
        if not app.debug:
            if not os.path.exists('logs'):
                os.mkdir('logs')
            file_handler = RotatingFileHandler('logs/assetify.log', maxBytes=10240, backupCount=10)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
            ))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)
            app.logger.setLevel(logging.INFO)
            app.logger.info('Assetify startup')

    return app