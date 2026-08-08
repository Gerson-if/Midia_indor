import re
from datetime import datetime, timezone

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app.blueprints.auth.forms import LoginForm
from app.blueprints.superadmin import superadmin_bp
from app.blueprints.superadmin.forms import TenantBlockForm, TenantCreateForm, TenantDomainForm
from app.extensions import db, limiter
from app.models import SiteSettings, Tenant, TenantDomain, TenantStatus, User, UserRole, normalize_domain
from app.utils.decorators import log_action

# ------------------------------------------------------------------ #
# Autenticação (separada do login de cliente: super admin não pertence
# a nenhum tenant, então não faz sentido reaproveitar o /login comum,
# que depende do domínio acessado).
# ------------------------------------------------------------------ #
@superadmin_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated and getattr(current_user, "is_super_admin", False):
        return redirect(url_for("superadmin.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email, role=UserRole.SUPER_ADMIN).first()

        if user and user.is_active_flag and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            log_action("auth.superadmin_login", entity_type="User", entity_id=user.id)
            db.session.commit()
            return redirect(url_for("superadmin.dashboard"))

        flash("E-mail ou senha incorretos.", "danger")

    return render_template("superadmin/login.html", form=form)


@superadmin_bp.route("/logout")
def logout():
    if current_user.is_authenticated:
        log_action("auth.superadmin_logout", entity_type="User", entity_id=current_user.id)
        db.session.commit()
        logout_user()
    return redirect(url_for("superadmin.login"))


# ------------------------------------------------------------------ #
# Dashboard / listagem de páginas
# ------------------------------------------------------------------ #
@superadmin_bp.route("/")
def dashboard():
    tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    stats = {
        "total": len(tenants),
        "active": sum(1 for t in tenants if not t.is_blocked),
        "blocked": sum(1 for t in tenants if t.is_blocked),
    }
    return render_template("superadmin/dashboard.html", tenants=tenants, stats=stats)


# ------------------------------------------------------------------ #
# Criar página nova
# ------------------------------------------------------------------ #
@superadmin_bp.route("/paginas/nova", methods=["GET", "POST"])
def tenant_new():
    form = TenantCreateForm()
    if form.validate_on_submit():
        email = form.owner_email.data.strip().lower()
        if User.query.filter_by(email=email).first():
            flash("Já existe um usuário com este e-mail.", "danger")
            return render_template("superadmin/tenant_form.html", form=form)

        domain_value = normalize_domain(form.domain.data) if form.domain.data else None
        if domain_value and TenantDomain.query.filter_by(domain=domain_value).first():
            flash("Este domínio já está em uso por outra página.", "danger")
            return render_template("superadmin/tenant_form.html", form=form)

        slug = (form.slug.data or "").strip().lower() or _slugify(form.name.data)
        slug = _unique_tenant_slug(slug)

        tenant = Tenant(name=form.name.data.strip(), slug=slug)
        db.session.add(tenant)
        db.session.flush()  # garante tenant.id antes de referenciá-lo abaixo

        owner = User(
            name=form.owner_name.data.strip(),
            email=email,
            role=UserRole.ADMIN,
            tenant_id=tenant.id,
        )
        owner.set_password(form.owner_password.data)
        db.session.add(owner)
        db.session.flush()
        tenant.owner_user_id = owner.id

        if domain_value:
            db.session.add(TenantDomain(tenant_id=tenant.id, domain=domain_value, is_primary=True))

        # Já cria a linha de configurações do site, com o nome informado,
        # para o painel do cliente abrir populado (em vez de em branco).
        db.session.add(SiteSettings(tenant_id=tenant.id, company_name=form.name.data.strip()))

        log_action(
            "tenant.created",
            entity_type="Tenant",
            entity_id=tenant.id,
            description=f"{tenant.name} (owner: {owner.email})",
            tenant_id=tenant.id,
        )
        db.session.commit()
        flash(f'Página "{tenant.name}" criada com sucesso.', "success")
        return redirect(url_for("superadmin.tenant_detail", tenant_id=tenant.id))

    return render_template("superadmin/tenant_form.html", form=form)


# ------------------------------------------------------------------ #
# Detalhe / domínios / bloqueio
# ------------------------------------------------------------------ #
@superadmin_bp.route("/paginas/<int:tenant_id>")
def tenant_detail(tenant_id):
    tenant = Tenant.query.filter_by(id=tenant_id).first_or_404()
    return render_template(
        "superadmin/tenant_detail.html",
        tenant=tenant,
        domain_form=TenantDomainForm(),
        block_form=TenantBlockForm(),
    )


@superadmin_bp.route("/paginas/<int:tenant_id>/dominios", methods=["POST"])
def tenant_add_domain(tenant_id):
    tenant = Tenant.query.filter_by(id=tenant_id).first_or_404()
    form = TenantDomainForm()
    if form.validate_on_submit():
        domain_value = normalize_domain(form.domain.data)
        if TenantDomain.query.filter_by(domain=domain_value).first():
            flash("Este domínio já está cadastrado (nesta ou em outra página).", "danger")
        else:
            if form.is_primary.data:
                TenantDomain.query.filter_by(tenant_id=tenant.id).update({"is_primary": False})
            db.session.add(
                TenantDomain(
                    tenant_id=tenant.id,
                    domain=domain_value,
                    is_primary=form.is_primary.data or not tenant.domains,
                )
            )
            log_action(
                "tenant.domain_added",
                entity_type="Tenant",
                entity_id=tenant.id,
                description=domain_value,
                tenant_id=tenant.id,
            )
            db.session.commit()
            flash(
                f'Domínio "{domain_value}" adicionado. Aponte o DNS dele (registro A) para o IP desta VPS '
                "que o site já entra no ar automaticamente, com HTTPS incluso.",
                "success",
            )
    else:
        flash("Não foi possível adicionar: verifique o domínio informado.", "danger")
    return redirect(url_for("superadmin.tenant_detail", tenant_id=tenant.id))


@superadmin_bp.route("/paginas/<int:tenant_id>/dominios/<int:domain_id>/excluir", methods=["POST"])
def tenant_remove_domain(tenant_id, domain_id):
    tenant = Tenant.query.filter_by(id=tenant_id).first_or_404()
    domain = TenantDomain.query.filter_by(id=domain_id, tenant_id=tenant.id).first_or_404()
    log_action(
        "tenant.domain_removed",
        entity_type="Tenant",
        entity_id=tenant.id,
        description=domain.domain,
        tenant_id=tenant.id,
    )
    db.session.delete(domain)
    db.session.commit()
    flash("Domínio removido.", "info")
    return redirect(url_for("superadmin.tenant_detail", tenant_id=tenant.id))


@superadmin_bp.route("/paginas/<int:tenant_id>/bloquear", methods=["POST"])
def tenant_block(tenant_id):
    tenant = Tenant.query.filter_by(id=tenant_id).first_or_404()
    form = TenantBlockForm()
    if form.validate_on_submit():
        tenant.status = TenantStatus.BLOCKED
        tenant.blocked_reason = form.reason.data.strip()
        tenant.blocked_at = datetime.now(timezone.utc)
        tenant.blocked_by_id = current_user.id
        log_action(
            "tenant.blocked",
            entity_type="Tenant",
            entity_id=tenant.id,
            description=tenant.blocked_reason,
            tenant_id=tenant.id,
        )
        db.session.commit()
        flash(f'Página "{tenant.name}" bloqueada. O site público dela sai do ar imediatamente.', "warning")
    else:
        flash("Informe o motivo do bloqueio.", "danger")
    return redirect(url_for("superadmin.tenant_detail", tenant_id=tenant.id))


@superadmin_bp.route("/paginas/<int:tenant_id>/desbloquear", methods=["POST"])
def tenant_unblock(tenant_id):
    tenant = Tenant.query.filter_by(id=tenant_id).first_or_404()
    tenant.status = TenantStatus.ACTIVE
    tenant.blocked_reason = None
    tenant.blocked_at = None
    tenant.blocked_by_id = None
    log_action("tenant.unblocked", entity_type="Tenant", entity_id=tenant.id, tenant_id=tenant.id)
    db.session.commit()
    flash(f'Página "{tenant.name}" desbloqueada.', "success")
    return redirect(url_for("superadmin.tenant_detail", tenant_id=tenant.id))


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #
def _slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "pagina"


def _unique_tenant_slug(base: str) -> str:
    slug = base
    suffix = 2
    while Tenant.query.filter_by(slug=slug).first() is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug
