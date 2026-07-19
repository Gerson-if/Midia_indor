"""
Instâncias únicas das extensões Flask.

Mantidas em módulo separado para evitar imports circulares entre
app/__init__.py, os blueprints e os models.
"""
from flask_bcrypt import Bcrypt
from flask_compress import Compress
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_talisman import Talisman
from flask_wtf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
csrf = CSRFProtect()
login_manager = LoginManager()
talisman = Talisman()
compress = Compress()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],  # definido via app.config["RATELIMIT_DEFAULT"]
)

login_manager.login_view = "auth.login"
login_manager.login_message = "Faça login para acessar esta página."
login_manager.login_message_category = "warning"
login_manager.session_protection = "strong"
