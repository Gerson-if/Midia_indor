import os

import click
from flask import Flask, g, request
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import get_config
from app.extensions import bcrypt, compress, csrf, db, limiter, login_manager, migrate, talisman
from app.utils.errors import register_error_handlers
from app.utils.legal_content import render_legal_content
from app.utils.logging import configure_logging
from app.utils.tenancy import current_tenant, enforce_tenant_gate, register_tenant_filter, resolve_tenant


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
    register_tenant_filter(app)
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
    compress.init_app(app)

    limiter.init_app(app)
    if app.config.get("TESTING") or app.config.get("RATELIMIT_ENABLED") is False:
        limiter.enabled = False

    # Talisman: cabeçalhos de segurança (CSP, HSTS, X-Content-Type-Options, etc.)
    # CSP restrita a 'self': todo o front-end (Tailwind, fontes, Chart.js,
    # AOS) é servido localmente a partir de app/static — sem dependência
    # de CDNs de terceiros, reduzindo a superfície de rede e melhorando
    # o tempo de carregamento (sem round-trips extras de DNS/TLS).
    csp = {
        "default-src": "'self'",
        "script-src": ["'self'", "'unsafe-inline'"],
        "style-src": ["'self'", "'unsafe-inline'"],
        "font-src": ["'self'"],
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
        from flask import g

        user = db.session.get(User, int(user_id))
        if user is None:
            return None
        # Rede de segurança: um usuário de uma página de cliente nunca é
        # considerado autenticado fora do domínio da própria página (o
        # cookie de sessão já é isolado por domínio pelo navegador, mas
        # isso cobre cenários de domínios compartilhados/alias mal
        # configurados). O super admin (tenant_id nulo) só "existe" fora
        # de qualquer tenant (painel /super).
        tenant_id = getattr(g, "tenant_id", None)
        if user.tenant_id is not None and tenant_id is not None and user.tenant_id != tenant_id:
            return None
        return user

    app.jinja_env.filters["legal_content"] = render_legal_content


def _register_blueprints(app: Flask) -> None:
    from app.blueprints.admin import admin_bp
    from app.blueprints.api import api_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.main import main_bp
    from app.blueprints.superadmin import superadmin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(superadmin_bp)


def _register_context_processors(app: Flask) -> None:
    @app.context_processor
    def inject_globals():
        from datetime import datetime, timezone

        from app.models import SiteSettings

        try:
            settings = SiteSettings.get_solo()
        except Exception:
            settings = None

        return {
            "APP_NAME": app.config.get("COMPANY_NAME"),
            "now_year": datetime.now(timezone.utc).year,
            "global_settings": settings,
            "current_tenant": current_tenant(),
        }

    # Cache por instância de app (não módulo): evita vazar valores entre
    # apps diferentes criados no mesmo processo (ex.: testes que chamam
    # create_app() várias vezes com static_folder/config diferentes).
    _static_asset_version_cache: dict[str, str] = {}

    @app.template_global("static_asset")
    def static_asset(filename: str) -> str:
        """
        URL de um arquivo estático "de build" (CSS/JS/vendor/ícone padrão)
        com cache-busting automático.

        O Nginx serve tudo em /static com "Cache-Control: public,
        immutable" por 30 dias (deploy/nginx*.conf.template) — ótimo para
        performance, mas sem isso o navegador de quem já visitou o site
        continua usando o CSS/JS antigo em cache por até 30 dias após
        cada atualização (ex.: alguém troca o tema em Configurações e o
        visitante não vê nada de diferente, mesmo dando F5, porque o
        style.css antigo — sem as regras do tema — ainda está em cache).
        Anexar "?v=<hora da última modificação do arquivo>" muda a URL
        sempre que o conteúdo muda, forçando o navegador a buscar a
        versão nova, sem precisar abrir mão do cache de 30 dias para
        quem não teve nada alterado.

        Não usar para arquivos enviados pelo admin (logo, favicon, mídia
        do Hero, imagens de galeria etc.) — esses já têm nome de arquivo
        próprio por upload e não precisam disso.

        A data de modificação é lida do disco (os.path.getmtime) só na
        PRIMEIRA vez que cada arquivo é pedido, e fica guardada em memória
        pelo resto da vida do processo — sem esse cache, toda página
        (inclusive as do painel admin, que chamam isso 8-9 vezes cada)
        faria uma chamada ao sistema de arquivos por asset, em toda
        requisição, para sempre, o que ia pesando o site conforme o
        tráfego crescesse. Como o processo é reiniciado a cada deploy
        (update.sh faz systemctl reload/start), o valor em cache nunca
        fica desatualizado: um deploy novo = processo novo = cache novo.
        """
        from flask import url_for

        if filename not in _static_asset_version_cache:
            version = ""
            try:
                file_path = os.path.join(app.static_folder, filename)
                version = str(int(os.path.getmtime(file_path)))
            except OSError:
                pass
            _static_asset_version_cache[filename] = version

        version = _static_asset_version_cache[filename]
        url = url_for("static", filename=filename)
        return f"{url}?v={version}" if version else url


def _register_request_hooks(app: Flask) -> None:
    @app.before_request
    def add_request_context():
        g.request_id = request.headers.get("X-Request-ID", os.urandom(8).hex())

    # Ordem importa: primeiro identifica o tenant pelo domínio, depois
    # decide se a requisição pode seguir (domínio desconhecido ou tenant
    # bloqueado interrompem aqui, antes de qualquer rota rodar). Como
    # before_request de nível de app sempre roda antes dos de blueprint
    # (ex.: admin_bp.require_login), isso vale também para o painel admin.
    app.before_request(resolve_tenant)
    app.before_request(enforce_tenant_gate)

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

    @app.cli.command("create-superadmin")
    def create_superadmin():
        """Cria (ou atualiza) o super admin -- dono do sistema, gerencia as páginas de clientes."""
        from app.models import User, UserRole

        name = os.environ.get("SUPERADMIN_NAME", "Super Admin")
        email = os.environ.get("SUPERADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("SUPERADMIN_PASSWORD")

        if not email or not password:
            print("Defina SUPERADMIN_EMAIL e SUPERADMIN_PASSWORD no ambiente antes de rodar este comando.")
            return

        user = User.query.filter_by(email=email).first()
        if user:
            user.set_password(password)
            user.role = UserRole.SUPER_ADMIN
            user.tenant_id = None
            user.is_active_flag = True
            print(f"Super admin '{email}' atualizado.")
        else:
            user = User(name=name, email=email, role=UserRole.SUPER_ADMIN)
            user.set_password(password)
            db.session.add(user)
            print(f"Super admin '{email}' criado. Acesse em /super/login.")
        db.session.commit()

    @app.cli.command("create-admin")
    @click.option("--tenant-slug", default=None, help="Página (tenant) a que este admin pertence.")
    def create_admin(tenant_slug):
        """
        Cria (ou atualiza) o usuário administrador de uma página, a partir
        das variáveis de ambiente. Mantém o instalador de página única
        funcionando: se a página informada (TENANT_SLUG, padrão "default")
        ainda não existir, ela é criada agora, com o domínio de DOMAIN (se
        definido) já associado. Para criar páginas adicionais depois, use
        o painel do super admin em /super.
        """
        from app.models import Tenant, TenantDomain, User, UserRole, normalize_domain

        name = os.environ.get("ADMIN_NAME", "Administrador")
        email = os.environ.get("ADMIN_EMAIL", "admin@nexomidia.com.br").lower()
        password = os.environ.get("ADMIN_PASSWORD")

        if not password:
            print("Defina ADMIN_PASSWORD no ambiente antes de rodar este comando.")
            return

        tenant_slug = tenant_slug or os.environ.get("TENANT_SLUG", "default")
        tenant = Tenant.query.filter_by(slug=tenant_slug).first()
        if tenant is None:
            tenant = Tenant(name=os.environ.get("COMPANY_NAME", "Minha Página"), slug=tenant_slug)
            db.session.add(tenant)
            db.session.flush()
            print(f"Página '{tenant.slug}' criada.")

        # Anexa o domínio do ambiente sempre que a página ainda não tiver
        # nenhum -- tanto para uma página recém-criada quanto para uma já
        # existente sem domínio (ex.: logo após a migração multi-tenant
        # rodar sobre um banco de uma instalação single-tenant antiga,
        # que cria a página "default" mas não sabe qual domínio ela usa,
        # já que isso vive no .env, não no banco).
        if not TenantDomain.query.filter_by(tenant_id=tenant.id).first():
            # SERVER_NAME é o nome histórico usado pelo instalador (deploy/scripts/
            # configure-env.sh); DOMAIN/PRIMARY_DOMAIN são aceitos como alternativa
            # para quem estiver configurando manualmente.
            domain_env = (
                os.environ.get("DOMAIN")
                or os.environ.get("PRIMARY_DOMAIN")
                or os.environ.get("SERVER_NAME")
            )
            import re as _re

            is_ip = domain_env and _re.match(r"^\d{1,3}(\.\d{1,3}){3}$", domain_env)
            if domain_env and not is_ip:
                db.session.add(
                    TenantDomain(tenant_id=tenant.id, domain=normalize_domain(domain_env), is_primary=True)
                )
                print(f"Domínio '{normalize_domain(domain_env)}' associado à página '{tenant.slug}'.")
            elif is_ip:
                print(
                    f"Aviso: '{domain_env}' parece ser um IP, não um domínio -- HTTPS automático (Caddy) "
                    "exige um domínio real. Cadastre o domínio pelo painel /super assim que tiver um; "
                    "por enquanto o acesso via IP fica só em HTTP."
                )
            else:
                print(
                    f"Aviso: a página '{tenant.slug}' ainda não tem nenhum domínio cadastrado. "
                    "O site fica inacessível até você cadastrar um em /super ou definir "
                    "DOMAIN/SERVER_NAME no ambiente e rodar este comando de novo."
                )

        user = User.query.filter_by(email=email).first()
        if user:
            user.set_password(password)
            user.role = UserRole.ADMIN
            user.tenant_id = tenant.id
            user.is_active_flag = True
            print(f"Usuário admin '{email}' atualizado (página: {tenant.slug}).")
        else:
            user = User(name=name, email=email, role=UserRole.ADMIN, tenant_id=tenant.id)
            user.set_password(password)
            db.session.add(user)
            print(f"Usuário admin '{email}' criado (página: {tenant.slug}).")
        db.session.flush()
        tenant.owner_user_id = user.id
        db.session.commit()

    @app.cli.command("seed-demo")
    @click.option("--tenant-slug", default="default", help="Página (tenant) a popular com conteúdo de demonstração.")
    def seed_demo(tenant_slug):
        """Popula o banco com conteúdo de demonstração (idempotente) para a página informada."""
        from app.models import Tenant
        from scripts.seed import run_seed

        tenant = Tenant.query.filter_by(slug=tenant_slug).first()
        if tenant is None:
            print(f"Página '{tenant_slug}' não encontrada. Rode 'flask create-admin' primeiro.")
            return

        run_seed(tenant.id)
        print(f"Seed de demonstração aplicado à página '{tenant.slug}'.")
