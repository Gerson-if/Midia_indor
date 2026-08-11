import re
from datetime import date, datetime, timezone

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app.blueprints.auth.forms import LoginForm
from app.blueprints.superadmin import superadmin_bp
from app.blueprints.superadmin.forms import (
    ChangeTemplateForm,
    InvoiceCreateForm,
    InvoiceItemForm,
    TenantBlockForm,
    TenantCreateForm,
    TenantDeleteForm,
    TenantDomainForm,
)
from app.extensions import db, limiter
from app.models import (
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    SiteSettings,
    Tenant,
    TenantDomain,
    TenantStatus,
    User,
    UserRole,
    normalize_domain,
)
from app.services.tenants import delete_tenant
from app.utils.decorators import log_action


@superadmin_bp.context_processor
def _inject_pending_invoices_count():
    if not getattr(current_user, "is_super_admin", False):
        return {}
    count = Invoice.query.filter_by(status=InvoiceStatus.PENDING).count()
    return {"pending_invoices_count": count}

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

        if form.template.data and form.template.data != "none":
            # Página nova abre com um modelo pronto (textos do Hero,
            # serviços, galeria, depoimentos, parceiros) de acordo com o
            # tipo de negócio escolhido, em vez de em branco -- mais fácil
            # do cliente/admin adaptar do que começar do zero. Mesmo
            # conteúdo aplicado pelo "flask seed-demo --template=...".
            from scripts.seed import run_seed

            run_seed(tenant.id, template=form.template.data)

        flash(f'Página "{tenant.name}" criada com sucesso.', "success")
        return redirect(url_for("superadmin.tenant_detail", tenant_id=tenant.id))

    return render_template("superadmin/tenant_form.html", form=form)


# ------------------------------------------------------------------ #
# Detalhe / domínios / bloqueio
# ------------------------------------------------------------------ #
@superadmin_bp.route("/paginas/<int:tenant_id>")
def tenant_detail(tenant_id):
    tenant = Tenant.query.filter_by(id=tenant_id).first_or_404()
    invoices = Invoice.query.filter_by(tenant_id=tenant.id).order_by(Invoice.due_date.desc()).all()
    return render_template(
        "superadmin/tenant_detail.html",
        tenant=tenant,
        domain_form=TenantDomainForm(),
        block_form=TenantBlockForm(),
        delete_form=TenantDeleteForm(),
        template_form=ChangeTemplateForm(),
        invoices=invoices,
    )


@superadmin_bp.route("/paginas/<int:tenant_id>/trocar-modelo", methods=["POST"])
def tenant_change_template(tenant_id):
    tenant = Tenant.query.filter_by(id=tenant_id).first_or_404()
    form = ChangeTemplateForm()
    if form.validate_on_submit():
        from scripts.seed import replace_template_content

        replace_template_content(tenant.id, form.template.data)
        log_action(
            "tenant.template_changed",
            entity_type="Tenant",
            entity_id=tenant.id,
            description=form.template.data,
            tenant_id=tenant.id,
        )
        db.session.commit()
        flash(f'Modelo de conteúdo da página "{tenant.name}" trocado.', "success")
    else:
        flash("Não foi possível trocar o modelo: selecione uma opção válida.", "danger")
    return redirect(url_for("superadmin.tenant_detail", tenant_id=tenant.id))


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
# Exclusão definitiva (irreversível) -- páginas que não são mais usadas.
# ------------------------------------------------------------------ #
@superadmin_bp.route("/paginas/<int:tenant_id>/excluir", methods=["POST"])
def tenant_delete(tenant_id):
    tenant = Tenant.query.filter_by(id=tenant_id).first_or_404()
    form = TenantDeleteForm()

    if not form.validate_on_submit() or form.confirm_slug.data.strip().lower() != tenant.slug:
        flash(
            f'Confirmação incorreta -- digite exatamente "{tenant.slug}" para excluir esta página.', "danger"
        )
        return redirect(url_for("superadmin.tenant_detail", tenant_id=tenant.id))

    name, slug = tenant.name, tenant.slug
    delete_tenant(tenant)  # já comita: apaga conteúdo/usuários/domínios e a página

    log_action(
        "tenant.deleted",
        entity_type="Tenant",
        entity_id=tenant_id,
        description=f"{name} ({slug})",
        tenant_id=None,  # a página não existe mais -- nada a referenciar
    )
    db.session.commit()

    flash(f'Página "{name}" excluída definitivamente.', "success")
    return redirect(url_for("superadmin.dashboard"))


# ------------------------------------------------------------------ #
# Faturamento -- faturas lançadas pelo super admin para os lojistas.
# ------------------------------------------------------------------ #
@superadmin_bp.route("/faturas")
def invoices_overview():
    status_filter = request.args.get("status", "pending")
    query = Invoice.query.join(Tenant)
    if status_filter == "pending":
        query = query.filter(Invoice.status == InvoiceStatus.PENDING)
    elif status_filter == "paid":
        query = query.filter(Invoice.status == InvoiceStatus.PAID)
    elif status_filter == "canceled":
        query = query.filter(Invoice.status == InvoiceStatus.CANCELED)
    # "all" não filtra

    invoices = query.order_by(Invoice.due_date.asc()).all()
    pending_count = Invoice.query.filter_by(status=InvoiceStatus.PENDING).count()
    overdue_count = sum(1 for i in Invoice.query.filter_by(status=InvoiceStatus.PENDING).all() if i.is_overdue)

    return render_template(
        "superadmin/invoices_overview.html",
        invoices=invoices,
        status_filter=status_filter,
        pending_count=pending_count,
        overdue_count=overdue_count,
    )


@superadmin_bp.route("/paginas/<int:tenant_id>/faturas/nova", methods=["GET", "POST"])
def invoice_new(tenant_id):
    tenant = Tenant.query.filter_by(id=tenant_id).first_or_404()
    form = InvoiceCreateForm()
    if form.validate_on_submit():
        invoice = Invoice(
            tenant_id=tenant.id,
            title=form.title.data.strip(),
            due_date=form.due_date.data,
            is_recurring=form.is_recurring.data,
            service_cutoff_at=form.service_cutoff_at.data,
            notes=(form.notes.data or "").strip() or None,
        )
        db.session.add(invoice)
        db.session.flush()
        log_action(
            "invoice.created",
            entity_type="Invoice",
            entity_id=invoice.id,
            description=f"{invoice.title} ({tenant.name})",
            tenant_id=tenant.id,
        )
        db.session.commit()
        flash('Fatura criada. Agora adicione os itens que discriminam o que está incluso.', "success")
        return redirect(url_for("superadmin.invoice_detail", invoice_id=invoice.id))

    return render_template("superadmin/invoice_form.html", form=form, tenant=tenant)


@superadmin_bp.route("/faturas/<int:invoice_id>")
def invoice_detail(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id).first_or_404()
    return render_template(
        "superadmin/invoice_detail.html",
        invoice=invoice,
        tenant=invoice.tenant,
        item_form=InvoiceItemForm(),
        today=date.today(),
    )


@superadmin_bp.route("/faturas/<int:invoice_id>/itens", methods=["POST"])
def invoice_add_item(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id).first_or_404()
    form = InvoiceItemForm()
    if form.validate_on_submit():
        next_order = len(invoice.items) + 1
        db.session.add(
            InvoiceItem(
                tenant_id=invoice.tenant_id,
                invoice_id=invoice.id,
                description=form.description.data.strip(),
                amount=form.amount.data,
                display_order=next_order,
            )
        )
        log_action(
            "invoice.item_added",
            entity_type="Invoice",
            entity_id=invoice.id,
            description=f"{form.description.data.strip()} (R$ {form.amount.data})",
            tenant_id=invoice.tenant_id,
        )
        db.session.commit()
        flash("Item adicionado.", "success")
    else:
        flash("Não foi possível adicionar o item: verifique a descrição e o valor.", "danger")
    return redirect(url_for("superadmin.invoice_detail", invoice_id=invoice.id))


@superadmin_bp.route("/faturas/<int:invoice_id>/itens/<int:item_id>/excluir", methods=["POST"])
def invoice_remove_item(invoice_id, item_id):
    invoice = Invoice.query.filter_by(id=invoice_id).first_or_404()
    item = InvoiceItem.query.filter_by(id=item_id, invoice_id=invoice.id).first_or_404()
    db.session.delete(item)
    log_action(
        "invoice.item_removed",
        entity_type="Invoice",
        entity_id=invoice.id,
        description=item.description,
        tenant_id=invoice.tenant_id,
    )
    db.session.commit()
    flash("Item removido.", "info")
    return redirect(url_for("superadmin.invoice_detail", invoice_id=invoice.id))


@superadmin_bp.route("/faturas/<int:invoice_id>/marcar-paga", methods=["POST"])
def invoice_mark_paid(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id).first_or_404()
    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = datetime.now(timezone.utc)
    log_action(
        "invoice.paid",
        entity_type="Invoice",
        entity_id=invoice.id,
        description=invoice.title,
        tenant_id=invoice.tenant_id,
    )
    db.session.commit()
    flash(f'Fatura "{invoice.title}" marcada como paga.', "success")
    return redirect(request.referrer or url_for("superadmin.tenant_detail", tenant_id=invoice.tenant_id))


@superadmin_bp.route("/faturas/<int:invoice_id>/cancelar", methods=["POST"])
def invoice_cancel(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id).first_or_404()
    invoice.status = InvoiceStatus.CANCELED
    log_action(
        "invoice.canceled",
        entity_type="Invoice",
        entity_id=invoice.id,
        description=invoice.title,
        tenant_id=invoice.tenant_id,
    )
    db.session.commit()
    flash(f'Fatura "{invoice.title}" cancelada.', "info")
    return redirect(request.referrer or url_for("superadmin.tenant_detail", tenant_id=invoice.tenant_id))


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
