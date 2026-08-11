"""
Multi-tenancy por domínio.

Como funciona, em 3 partes:

1. resolve_tenant() (before_request): olha o cabeçalho Host da requisição,
   procura em TenantDomain e guarda o tenant encontrado em g.tenant /
   g.tenant_id. Rotas do super admin (blueprint "superadmin") nunca
   resolvem tenant -- o super admin enxerga tudo, de qualquer domínio.

2. register_tenant_filter() (chamado uma vez em create_app): registra um
   listener no evento do_orm_execute do SQLAlchemy que injeta
   automaticamente "WHERE tenant_id = g.tenant_id" em toda consulta ORM
   feita a um model que herda de TenantScopedMixin -- inclusive
   relacionamentos carregados via lazy-load. Isso é o que permite manter
   as ~50 consultas já existentes em main/admin/api (Service.query...,
   GalleryItem.query..., etc.) funcionando sem alteração nenhuma: elas
   passam a devolver só os dados do tenant certo automaticamente.

3. enforce_tenant_gate() (before_request, registrado depois do resolve):
   se o domínio não corresponde a nenhum tenant cadastrado, ou o tenant
   está bloqueado, interrompe a requisição pública com uma página
   genérica -- sem revelar o motivo. Login e o próprio painel admin do
   tenant continuam acessíveis mesmo bloqueado, para que o administrador
   daquela página (e só ele) veja o aviso de pendência.

Observação de segurança: Model.query.get_or_404()/db.session.get() usam
um caminho rápido do SQLAlchemy que NÃO passa pelo evento do_orm_execute
(limitação conhecida do with_loader_criteria). Por isso, nas rotas que
buscam um registro por id, usamos "<Model>.query.filter_by(id=...)"
em vez de ".get()/.get_or_404()" -- só assim o filtro de tenant também
protege essas buscas contra acesso cruzado entre tenants (IDOR).
"""
from flask import abort, g, render_template, request
from sqlalchemy import event
from sqlalchemy.orm import with_loader_criteria

from app.extensions import db
from app.models.tenant import Tenant, TenantDomain, TenantScopedMixin, TenantStatus

# Prefixos de rota que nunca são resolvidos/bloqueados por tenant: painel
# do super admin (não pertence a nenhum tenant), assets estáticos,
# endpoints internos (Caddy) e o healthcheck (chamado por load
# balancer/orquestrador/instalador direto no IP:porta do Gunicorn,
# sem Host correspondendo a nenhum domínio cadastrado -- sem essa
# exceção, ele sempre cai no "domínio desconhecido" e devolve 404,
# mesmo com a aplicação saudável).
_TENANT_EXEMPT_PREFIXES = ("/static", "/internal", "/healthz")


def _current_host() -> str:
    # request.host já inclui a porta (ex.: "localhost:5000"); comparamos
    # só o hostname, que é o que é de fato cadastrado em TenantDomain.
    return request.host.split(":")[0].lower()


def register_tenant_filter(app):
    """Registra o filtro global de tenant no evento do_orm_execute da sessão."""

    @event.listens_for(db.session, "do_orm_execute")
    def _apply_tenant_filter(execute_state):
        if not execute_state.is_select:
            return
        if execute_state.execution_options.get("skip_tenant_filter"):
            return
        tenant_id = getattr(g, "tenant_id", None)
        if tenant_id is None:
            return
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                TenantScopedMixin,
                lambda cls: cls.tenant_id == tenant_id,
                include_aliases=True,
            )
        )


def resolve_tenant():
    """before_request: identifica o tenant pelo domínio da requisição."""
    g.tenant = None
    g.tenant_id = None

    if request.blueprint == "superadmin" or request.path.startswith(_TENANT_EXEMPT_PREFIXES):
        return

    host = _current_host()
    domain = TenantDomain.query.filter_by(domain=host).first()
    if domain is not None:
        g.tenant = domain.tenant
        g.tenant_id = domain.tenant_id


def enforce_tenant_gate():
    """before_request: bloqueia acesso público quando o domínio não tem
    tenant cadastrado ou o tenant está bloqueado por pendência."""
    if request.blueprint == "superadmin" or request.path.startswith(_TENANT_EXEMPT_PREFIXES):
        return

    # Domínio desconhecido (ainda não configurado no super admin, ou
    # aponta pra essa VPS por engano): mesma página genérica, sem detalhe.
    if g.tenant is None:
        return render_template("errors/tenant_unavailable.html", blocked=False), 404

    if g.tenant.status == TenantStatus.BLOCKED:
        # O painel admin (login incluso) continua acessível -- é lá que o
        # administrador daquela página vê o aviso de pendência. As demais
        # rotas (site público e API pública) caem na página genérica --
        # "blocked=True" só troca o tom da mensagem (avisa que o
        # responsável já está ciente), nunca o motivo real do bloqueio.
        if request.path.startswith("/admin") or request.path.startswith("/login") or request.path.startswith("/logout"):
            return None
        return render_template("errors/tenant_unavailable.html", blocked=True), 503


def current_tenant() -> Tenant | None:
    return getattr(g, "tenant", None)
