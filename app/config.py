"""
Configurações da aplicação, separadas por ambiente.

A escolha do ambiente é feita via variável FLASK_ENV (development, testing
ou production) e a classe correspondente é retornada por get_config().

Boas práticas aplicadas:
- Nenhum segredo hard-coded: tudo vem de variáveis de ambiente (.env).
- SQLite apenas para desenvolvimento/testes; PostgreSQL em produção.
- Pool de conexões configurável e "pre_ping" para evitar conexões mortas.
- Cookies de sessão seguros por padrão em produção (HttpOnly, Secure, SameSite).
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(env_value, default=False):
    if env_value is None:
        return default
    return str(env_value).strip().lower() in {"1", "true", "yes", "on"}


def _list(env_value, default=None):
    if not env_value:
        return default or []
    return [item.strip() for item in env_value.split(",") if item.strip()]


class BaseConfig:
    """Configuração compartilhada por todos os ambientes."""

    # ---- Segurança / Sessão ----
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-insegura-troque-me")
    SECURITY_PASSWORD_SALT = os.environ.get("SECURITY_PASSWORD_SALT", "dev-salt-troque-me")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = _bool(os.environ.get("REMEMBER_COOKIE_SECURE"), False)
    REMEMBER_COOKIE_DURATION = timedelta(days=14)

    PERMANENT_SESSION_LIFETIME = timedelta(
        minutes=int(os.environ.get("PERMANENT_SESSION_LIFETIME_MINUTES", 60))
    )
    SESSION_REFRESH_EACH_REQUEST = True

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # segue a validade da sessão

    # ---- Banco de dados ----
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": _bool(os.environ.get("SQLALCHEMY_POOL_PRE_PING"), True),
    }

    # ---- Uploads ----
    UPLOAD_FOLDER = str(BASE_DIR / os.environ.get("UPLOAD_FOLDER", "app/static/uploads"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", 8)) * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = set(
        _list(os.environ.get("ALLOWED_IMAGE_EXTENSIONS"), ["jpg", "jpeg", "png", "webp", "gif"])
    )
    ALLOWED_VIDEO_EXTENSIONS = set(
        _list(os.environ.get("ALLOWED_VIDEO_EXTENSIONS"), ["mp4", "webm"])
    )

    # ---- Rate limiting ----
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "200 per day;50 per hour")
    RATELIMIT_HEADERS_ENABLED = True

    # ---- Empresa / WhatsApp (usado nos templates e geração de mensagens) ----
    COMPANY_NAME = os.environ.get("COMPANY_NAME", "Nexo Mídia")
    COMPANY_WHATSAPP = os.environ.get("COMPANY_WHATSAPP", "5567999990000")
    COMPANY_EMAIL = os.environ.get("COMPANY_EMAIL", "contato@nexomidia.com.br")
    COMPANY_PHONE = os.environ.get("COMPANY_PHONE", "(67) 3241-5050")
    COMPANY_ADDRESS = os.environ.get("COMPANY_ADDRESS", "Campo Grande, MS")

    # ---- Logs ----
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_DIR = str(BASE_DIR / os.environ.get("LOG_DIR", "logs"))
    LOG_TO_STDOUT = _bool(os.environ.get("LOG_TO_STDOUT"), True)

    # ---- CORS ----
    CORS_ORIGINS = _list(os.environ.get("CORS_ORIGINS"), [])

    # ---- Proxy / HTTPS ----
    BEHIND_PROXY = _bool(os.environ.get("BEHIND_PROXY"), False)
    FORCE_HTTPS = _bool(os.environ.get("FORCE_HTTPS"), False)

    # ---- Paginação padrão da API/admin ----
    ITEMS_PER_PAGE = 20

    JSON_SORT_KEYS = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TESTING = False
    ENV = "development"
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'dev.sqlite3'}"
    )
    WTF_CSRF_ENABLED = True
    FORCE_HTTPS = False


class TestingConfig(BaseConfig):
    DEBUG = False
    TESTING = True
    ENV = "testing"
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    WTF_CSRF_ENABLED = False  # simplifica os testes de submissão de formulário
    RATELIMIT_ENABLED = False
    BCRYPT_LOG_ROUNDS = 4  # hashing mais rápido nos testes


class ProductionConfig(BaseConfig):
    DEBUG = False
    TESTING = False
    ENV = "production"

    # Não lê/valida DATABASE_URL na definição da classe: isso rodaria
    # sempre que o módulo config.py fosse importado, mesmo quando o
    # ambiente ativo é development/testing (quebrando o import inteiro
    # à toa). A validação real acontece em validate(), chamado pelo
    # app factory apenas quando ProductionConfig é de fato selecionado.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "")
    SQLALCHEMY_ENGINE_OPTIONS = {
        **BaseConfig.SQLALCHEMY_ENGINE_OPTIONS,
        "pool_size": int(os.environ.get("SQLALCHEMY_POOL_SIZE", 10)),
        "max_overflow": int(os.environ.get("SQLALCHEMY_MAX_OVERFLOW", 20)),
        "pool_recycle": int(os.environ.get("SQLALCHEMY_POOL_RECYCLE", 1800)),
    }

    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    FORCE_HTTPS = _bool(os.environ.get("FORCE_HTTPS"), True)

    @classmethod
    def validate(cls):
        if not cls.SQLALCHEMY_DATABASE_URI:
            raise RuntimeError(
                "DATABASE_URL é obrigatória em produção (use PostgreSQL). "
                "Configure a variável de ambiente antes de iniciar a aplicação."
            )
        insecure_defaults = {"dev-key-insegura-troque-me", "dev-salt-troque-me"}
        if cls.SECRET_KEY in insecure_defaults:
            raise RuntimeError("SECRET_KEY insegura detectada em produção. Defina uma chave forte.")


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env_name: str | None = None):
    env_name = (env_name or os.environ.get("FLASK_ENV") or "development").lower()
    return CONFIG_MAP.get(env_name, DevelopmentConfig)
