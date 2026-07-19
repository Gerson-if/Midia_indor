import os

from flask import Flask, g, request
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import get_config
from app.extensions import bcrypt, csrf, db, limiter, login_manager, migrate, talisman
from app.utils.errors import register_error_handlers
from app.utils.logging import configure_logging


def create_app(env_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    config_class = get_config(env_name)
    app.config.from_object(config_class)

    if hasattr(config_class, "validate"):
        config_class.validate()

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    configure_logging(app)

    if app.config.get("BEHIND_PROXY"):
        # Confia nos cabeçalhos X-Forwarded-* enviados pelo Nginx (1 proxy à frente).
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    _init_extensions(app)
    _register_blueprints(app)
    _register_context_processors(app)
    _register_request_hooks(app)
    _register_cli(app)

    register_error_handlers(app)

    app.logger.info("Aplicação inicializada com sucesso (ambiente=%s)", app.config.get("ENV"))
    return app


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    limiter.init_app(app)
    if app.config.get("TESTING") or app.config.get("RATELIMIT_ENABLED") is False:
        limiter.enabled = False

    # Talisman: cabeçalhos de segurança (CSP, HSTS, X-Content-Type-Options, etc.)
    # CSP permissiva o suficiente para os CDNs usados pelo front-end atual
    # (Tailwind CDN, Google Fonts, Alpine.js, Chart.js, AOS).
    csp = {
        "default-src": "'self'",
        "script-src": [
            "'self'",
            "'unsafe-inline'",
            "https://cdn.tailwindcss.com",
            "https://cdn.jsdelivr.net",
            "https://unpkg.com",
        ],
        "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://unpkg.com"],
        "font-src": ["'self'", "https://fonts.gstatic.com"],
        "img-src": ["'self'", "data:", "blob:"],
        "media-src": ["'self'", "blob:"],
        "connect-src": ["'self'"],
    }
    talisman.init_app(
        app,
        force_https=app.config.get("FORCE_HTTPS", False),
        content_security_policy=csp,
        content_security_policy_nonce_in=[],
        strict_transport_security=app.config.get("FORCE_HTTPS", False),
        session_cookie_secure=app.config.get("SESSION_COOKIE_SECURE", False),
    )

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))


def _register_blueprints(app: Flask) -> None:
    from app.blueprints.admin import admin_bp
    from app.blueprints.api import api_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.main import main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)


def _register_context_processors(app: Flask) -> None:
    @app.context_processor
    def inject_globals():
        from datetime import datetime, timezone

        return {
            "APP_NAME": app.config.get("COMPANY_NAME"),
            "now_year": datetime.now(timezone.utc).year,
        }


def _register_request_hooks(app: Flask) -> None:
    @app.before_request
    def add_request_context():
        g.request_id = request.headers.get("X-Request-ID", os.urandom(8).hex())

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        # Camada extra além do Talisman (defesa em profundidade).
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()


def _register_cli(app: Flask) -> None:
    """Comandos de linha de comando: flask create-admin, flask seed-demo."""

    @app.cli.command("create-admin")
    def create_admin():
        """Cria (ou atualiza) o usuário administrador a partir das variáveis de ambiente."""
        from app.models import User, UserRole

        name = os.environ.get("ADMIN_NAME", "Administrador")
        email = os.environ.get("ADMIN_EMAIL", "admin@nexomidia.com.br").lower()
        password = os.environ.get("ADMIN_PASSWORD")

        if not password:
            print("Defina ADMIN_PASSWORD no ambiente antes de rodar este comando.")
            return

        user = User.query.filter_by(email=email).first()
        if user:
            user.set_password(password)
            user.role = UserRole.ADMIN
            user.is_active_flag = True
            print(f"Usuário admin '{email}' atualizado.")
        else:
            user = User(name=name, email=email, role=UserRole.ADMIN)
            user.set_password(password)
            db.session.add(user)
            print(f"Usuário admin '{email}' criado.")
        db.session.commit()

    @app.cli.command("seed-demo")
    def seed_demo():
        """Popula o banco com conteúdo de demonstração (idempotente)."""
        from scripts.seed import run_seed

        run_seed()
        print("Seed de demonstração aplicado.")
