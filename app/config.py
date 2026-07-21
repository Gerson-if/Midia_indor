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
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", 80)) * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = set(
        _list(os.environ.get("ALLOWED_IMAGE_EXTENSIONS"), ["jpg", "jpeg", "png", "webp", "gif"])
    )
    ALLOWED_VIDEO_EXTENSIONS = set(
        _list(os.environ.get("ALLOWED_VIDEO_EXTENSIONS"), ["mp4", "webm"])
    )

    # ---- Rate limiting ----
    # "memory://" guarda os contadores no processo (dict em memória): funciona
    # bem para um único processo, mas o Gunicorn de produção roda vários
    # workers (deploy/gunicorn.conf.py) — cada worker é um PROCESSO separado
    # com sua própria memória, então cada um mantém sua própria contagem.
    # Resultado: o mesmo cliente pode ser liberado num worker e bloqueado
    # noutro para a mesma janela de tempo, e a reciclagem periódica dos
    # workers (max_requests) zera contadores no meio da janela — um
    # comportamento inconsistente de "às vezes libera, às vezes nega" bem
    # difícil de diagnosticar sob carga concorrente. Use um Redis
    # (RATELIMIT_STORAGE_URI=redis://...) em produção para contagem
    # compartilhada e consistente entre todos os workers/processos; veja o
    # aviso emitido em ProductionConfig.validate() quando isso não estiver
    # configurado.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    # Limites elevados para acomodar acesso concorrente legítimo de vários
    # usuários por trás do mesmo IP público (rede corporativa, shopping,
    # NAT de operadora móvel) — comum neste tipo de negócio (painéis de
    # mídia indoor instalados em locais com várias pessoas na mesma rede).
    # O valor anterior (200/dia; 50/hora) por IP já era insuficiente para
    # UM único usuário navegando normalmente, e ficava pior ainda quando
    # várias pessoas atrás do mesmo IP acessavam ao mesmo tempo — todas
    # elas compartilhando (e esgotando) a mesma cota, gerando exatamente
    # o erro 429 "Muitas requisições" relatado em acessos simultâneos.
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "2000 per day;400 per hour")
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

    # pool_size/max_overflow só são aceitos pelo QueuePool (Postgres).
    # SQLite usa StaticPool (":memory:") ou um pool que não aceita esses
    # argumentos — passá-los faz create_engine() estourar TypeError e
    # derruba a aplicação inteira antes de processar qualquer rota.
    # Isso quebrava exatamente o caso de testar ProductionConfig com
    # SQLite (sem PostgreSQL disponível).
    if SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS = dict(BaseConfig.SQLALCHEMY_ENGINE_OPTIONS)
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            **BaseConfig.SQLALCHEMY_ENGINE_OPTIONS,
            "pool_size": int(os.environ.get("SQLALCHEMY_POOL_SIZE", 10)),
            "max_overflow": int(os.environ.get("SQLALCHEMY_MAX_OVERFLOW", 20)),
            "pool_recycle": int(os.environ.get("SQLALCHEMY_POOL_RECYCLE", 1800)),
        }

    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    FORCE_HTTPS = _bool(os.environ.get("FORCE_HTTPS"), True)

    # Em produção o Flask roda atrás do Nginx (ver deploy/nginx.conf), que
    # encaminha X-Forwarded-For/Proto/Host/Port. Sem confiar nesses
    # cabeçalhos (via ProxyFix, ativado no app factory quando BEHIND_PROXY
    # é verdadeiro), o Werkzeug monta redirecionamentos e URLs absolutas
    # usando o host/porta interno do Gunicorn (127.0.0.1:8000) em vez do
    # domínio público — quebrando rotas e redirecionamentos assim que a
    # aplicação sai do localhost. Continua sobrescrevível via variável de
    # ambiente para quem não usa Nginx na frente.
    BEHIND_PROXY = _bool(os.environ.get("BEHIND_PROXY"), True)

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

        if cls.RATELIMIT_STORAGE_URI.startswith("memory://"):
            # Não é um erro fatal (a aplicação continua funcionando com um
            # único worker), mas com múltiplos workers do Gunicorn (o padrão
            # em produção) cada processo mantém sua própria contagem de rate
            # limit, causando bloqueios inconsistentes sob acesso concorrente
            # — avisamos alto e claro no log de inicialização em vez de
            # deixar isso passar silenciosamente.
            import logging

            logging.getLogger("app.startup").warning(
                "RATELIMIT_STORAGE_URI está usando 'memory://' em produção. "
                "Com múltiplos workers do Gunicorn, cada processo conta as "
                "requisições separadamente, causando bloqueios (429 'Muitas "
                "requisições') inconsistentes sob acesso concorrente. "
                "Configure um Redis (RATELIMIT_STORAGE_URI=redis://host:6379/0) "
                "para contagem compartilhada entre workers."
            )


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env_name: str | None = None):
    env_name = (env_name or os.environ.get("FLASK_ENV") or "development").lower()
    return CONFIG_MAP.get(env_name, DevelopmentConfig)
