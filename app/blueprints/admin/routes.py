import re

from flask import abort, current_app, flash, g, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.admin import admin_bp
from app.blueprints.admin.forms import (
    CustomSectionForm,
    CustomSectionItemForm,
    GalleryItemForm,
    GalleryRecommendationForm,
    PartnerForm,
    ProposalStatusForm,
    ServiceForm,
    SETTINGS_GROUPS,
    TestimonialForm,
    UserForm,
)
from app.extensions import db
from app.models import (
    AuditLog,
    CustomSection,
    CustomSectionItem,
    GalleryItem,
    GalleryRecommendation,
    Invoice,
    PageView,
    Partner,
    Proposal,
    Service,
    SiteSettings,
    Testimonial,
    User,
    UserRole,
)
from app.models.proposal import ProposalStatus
from app.services.uploads import UploadError, delete_upload, save_favicon, save_image, save_video
from app.services.whatsapp import build_client_whatsapp_link
from app.utils.decorators import admin_required, log_action, roles_required
from app.utils.legal_content import normalize_newlines

# Âncoras já usadas pelas seções fixas do site (index.html) — uma seção
# personalizada não pode gerar um slug igual a um desses, senão dois
# elementos com o mesmo id="" quebram a navegação por link (#âncora) e o
# scroll pode acabar levando para o lugar errado.
RESERVED_SLUGS = {"topo", "hero", "servicos", "galeria", "depoimentos", "contato"}
from sqlalchemy.orm.exc import StaleDataError

STAFF_ROLES = (UserRole.ADMIN, UserRole.EDITOR, UserRole.VIEWER)
EDIT_ROLES = (UserRole.ADMIN, UserRole.EDITOR)


# ------------------------------------------------------------------ #
# Dashboard
# ------------------------------------------------------------------ #
@admin_bp.route("/")
@roles_required(*STAFF_ROLES)
def dashboard():
    from datetime import datetime, timedelta, timezone

    total_proposals = Proposal.query.count()
    new_proposals = Proposal.query.filter_by(status=ProposalStatus.NOVO).count()
    converted = Proposal.query.filter_by(status=ProposalStatus.CONVERTIDO).count()
    recent_proposals = Proposal.query.order_by(Proposal.created_at.desc()).limit(6).all()

    # ---- Dados para o gráfico de status (donut) ----
    from app.models.proposal import STATUS_LABELS

    status_counts_raw = dict(
        db.session.query(Proposal.status, db.func.count(Proposal.id)).group_by(Proposal.status).all()
    )
    status_chart = {
        "labels": [STATUS_LABELS[s] for s in ProposalStatus],
        "data": [status_counts_raw.get(s, 0) for s in ProposalStatus],
    }

    # ---- Dados para o gráfico de solicitações nos últimos 14 dias ----
    # Bucketamento feito em Python (não via SQL) para evitar incompatibilidade
    # entre datetime "aware" e "naive" que o SQLite pode introduzir ao
    # persistir/ler colunas DateTime (o PostgreSQL não tem esse problema,
    # mas mantemos a mesma lógica para funcionar de forma idêntica em ambos).
    #
    # Antes esse bucketamento buscava TODAS as propostas já criadas
    # (Proposal.query.all() dos created_at, sem nenhum LIMIT/filtro) só
    # para montar um gráfico dos últimos 14 dias — e essa é a página mais
    # visitada do painel (dashboard, carregada a cada login e a cada F5).
    # Conforme a base de solicitações cresce com o uso normal do sistema,
    # essa consulta ficava progressivamente mais lenta, deixando o painel
    # inteiro mais pesado com o tempo. Como created_at já é indexado,
    # buscamos da mais recente para a mais antiga e paramos assim que
    # saímos da janela de 14 dias — nunca lê mais linhas do que precisa,
    # não importa quantos milhares de propostas existam no total.
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    oldest_day = days[0]
    counts_by_day = {d: 0 for d in days}

    recent_created_ats = (
        db.session.query(Proposal.created_at).order_by(Proposal.created_at.desc()).yield_per(500)
    )
    for (created_at,) in recent_created_ats:
        if created_at is None:
            continue
        day = created_at.date()
        if day < oldest_day:
            break
        if day in counts_by_day:
            counts_by_day[day] += 1

    timeline_chart = {
        "labels": [d.strftime("%d/%m") for d in days],
        "data": [counts_by_day[d] for d in days],
    }

    # ---- Visitas do site (últimos 30 dias): visualizações, visitantes
    # únicos, tempo médio na página e de onde vêm -- ajuda a cruzar picos
    # de tráfego com picos de solicitações recebidas. ----
    window_30d = datetime.now(timezone.utc) - timedelta(days=30)

    page_views_30d = PageView.query.filter(PageView.created_at >= window_30d).count()
    unique_visitors_30d = (
        db.session.query(db.func.count(db.distinct(PageView.session_id)))
        .filter(PageView.created_at >= window_30d)
        .scalar()
        or 0
    )
    avg_duration_raw = (
        db.session.query(db.func.avg(PageView.duration_seconds))
        .filter(PageView.created_at >= window_30d, PageView.duration_seconds.isnot(None))
        .scalar()
    )
    avg_duration_seconds = int(avg_duration_raw) if avg_duration_raw else 0
    if avg_duration_seconds >= 60:
        avg_duration_display = f"{avg_duration_seconds // 60}m {avg_duration_seconds % 60:02d}s"
    else:
        avg_duration_display = f"{avg_duration_seconds}s"

    # Mesmo bucketamento/janela de 14 dias já calculados acima para as
    # solicitações (days/oldest_day) -- os dois gráficos ficam lado a lado
    # com o eixo X idêntico, então dá pra comparar visualmente picos.
    views_by_day = {d: 0 for d in days}
    recent_view_created_ats = (
        db.session.query(PageView.created_at).order_by(PageView.created_at.desc()).yield_per(500)
    )
    for (created_at,) in recent_view_created_ats:
        if created_at is None:
            continue
        day = created_at.date()
        if day < oldest_day:
            break
        if day in views_by_day:
            views_by_day[day] += 1

    views_timeline_chart = {
        "labels": [d.strftime("%d/%m") for d in days],
        "data": [views_by_day[d] for d in days],
    }

    # ---- Origem do tráfego (top 6 + "Outros") ----
    TOP_SOURCES_LIMIT = 6
    source_rows = (
        db.session.query(PageView.referrer_source, db.func.count(PageView.id))
        .filter(PageView.created_at >= window_30d)
        .group_by(PageView.referrer_source)
        .order_by(db.func.count(PageView.id).desc())
        .all()
    )
    top_sources = [(label or "Direto", count) for label, count in source_rows[:TOP_SOURCES_LIMIT]]
    other_count = sum(count for _, count in source_rows[TOP_SOURCES_LIMIT:])
    if other_count:
        top_sources.append(("Outros", other_count))
    max_source_count = max((count for _, count in top_sources), default=0)

    return render_template(
        "admin/dashboard.html",
        total_proposals=total_proposals,
        new_proposals=new_proposals,
        converted=converted,
        recent_proposals=recent_proposals,
        active_gallery=GalleryItem.query.filter_by(is_active=True).count(),
        active_partners=Partner.query.filter_by(is_active=True).count(),
        status_chart=status_chart,
        timeline_chart=timeline_chart,
        page_views_30d=page_views_30d,
        unique_visitors_30d=unique_visitors_30d,
        avg_duration_display=avg_duration_display,
        views_timeline_chart=views_timeline_chart,
        top_sources=top_sources,
        max_source_count=max_source_count,
    )


# ------------------------------------------------------------------ #
# Solicitações (Proposals)
# ------------------------------------------------------------------ #
@admin_bp.route("/solicitacoes")
@roles_required(*STAFF_ROLES)
def proposals_list():
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "").strip()
    search = request.args.get("q", "").strip()

    query = Proposal.query
    if status_filter and status_filter in {s.value for s in ProposalStatus}:
        query = query.filter(Proposal.status == ProposalStatus(status_filter))
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                Proposal.name.ilike(like),
                Proposal.email.ilike(like),
                Proposal.phone.ilike(like),
                Proposal.company_name.ilike(like),
                Proposal.public_ref.ilike(like),
            )
        )

    pagination = query.order_by(Proposal.created_at.desc()).paginate(
        page=page, per_page=current_app.config["ITEMS_PER_PAGE"], error_out=False
    )

    return render_template(
        "admin/proposals_list.html",
        pagination=pagination,
        proposals=pagination.items,
        status_filter=status_filter,
        search=search,
        statuses=list(ProposalStatus),
    )


@admin_bp.route("/solicitacoes/<int:proposal_id>")
@roles_required(*STAFF_ROLES)
def proposal_detail(proposal_id):
    proposal = Proposal.query.filter_by(id=proposal_id).first_or_404()
    form = ProposalStatusForm(status=proposal.status.value, internal_notes=proposal.internal_notes, version_id=proposal.version_id)
    whatsapp_link = build_client_whatsapp_link(proposal, current_app.config["COMPANY_NAME"])
    history = (
        # AuditLog não herda TenantScopedMixin (algumas entradas são do
        # super admin, sem tenant) — aqui o filtro precisa ser explícito,
        # senão um "proposal.id" que colide com o de outra página vazaria
        # entradas de auditoria de um tenant para outro.
        AuditLog.query.filter_by(entity_type="Proposal", entity_id=str(proposal.id), tenant_id=proposal.tenant_id)
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "admin/proposal_detail.html",
        proposal=proposal,
        form=form,
        whatsapp_link=whatsapp_link,
        history=history,
        statuses=list(ProposalStatus),
    )


@admin_bp.route("/solicitacoes/<int:proposal_id>/status", methods=["POST"])
@roles_required(*EDIT_ROLES)
def proposal_update_status(proposal_id):
    proposal = Proposal.query.filter_by(id=proposal_id).first_or_404()
    form = ProposalStatusForm()

    if not form.validate_on_submit():
        flash("Não foi possível atualizar: verifique os dados informados.", "danger")
        return redirect(url_for("admin.proposal_detail", proposal_id=proposal.id))

    # Controle de concorrência otimista: se outro admin alterou o registro
    # entre a abertura da tela e este submit, rejeitamos e pedimos recarregar.
    if form.version_id.data is not None and form.version_id.data != proposal.version_id:
        flash(
            "Este registro foi alterado por outro usuário enquanto você editava. "
            "A página foi recarregada com os dados mais recentes.",
            "warning",
        )
        return redirect(url_for("admin.proposal_detail", proposal_id=proposal.id))

    old_status = proposal.status
    new_status = ProposalStatus(form.status.data)
    proposal.status = new_status
    proposal.internal_notes = form.internal_notes.data
    if new_status == ProposalStatus.CONTATADO and old_status != ProposalStatus.CONTATADO:
        from datetime import datetime, timezone

        proposal.contacted_at = datetime.now(timezone.utc)
        proposal.contacted_by_id = current_user.id

    try:
        log_action(
            "proposal.status_changed",
            entity_type="Proposal",
            entity_id=proposal.id,
            description=f"Status alterado de '{old_status.value}' para '{new_status.value}'",
            old_status=old_status.value,
            new_status=new_status.value,
        )
        db.session.commit()
        flash("Solicitação atualizada com sucesso.", "success")
    except StaleDataError:
        db.session.rollback()
        flash("Conflito de edição detectado. Recarregue a página e tente novamente.", "warning")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Erro ao atualizar status da proposta %s", proposal_id)
        flash("Erro ao salvar as alterações.", "danger")

    return redirect(url_for("admin.proposal_detail", proposal_id=proposal.id))


@admin_bp.route("/solicitacoes/<int:proposal_id>/whatsapp")
@roles_required(*STAFF_ROLES)
def proposal_whatsapp_redirect(proposal_id):
    """Registra em auditoria o contato e redireciona para o WhatsApp do cliente."""
    proposal = Proposal.query.filter_by(id=proposal_id).first_or_404()
    link = build_client_whatsapp_link(proposal, current_app.config["COMPANY_NAME"])
    log_action(
        "proposal.whatsapp_contact",
        entity_type="Proposal",
        entity_id=proposal.id,
        description=f"Contato iniciado via WhatsApp com {proposal.name}",
    )
    db.session.commit()
    return redirect(link)


@admin_bp.route("/solicitacoes/<int:proposal_id>/excluir", methods=["POST"])
@roles_required(UserRole.ADMIN)
def proposal_delete(proposal_id):
    proposal = Proposal.query.filter_by(id=proposal_id).first_or_404()
    log_action(
        "proposal.deleted",
        entity_type="Proposal",
        entity_id=proposal.id,
        description=f"Solicitação de {proposal.name} ({proposal.email}) excluída",
    )
    db.session.delete(proposal)
    db.session.commit()
    flash("Solicitação excluída.", "info")
    return redirect(url_for("admin.proposals_list"))


# ------------------------------------------------------------------ #
# Conteúdo do site: Serviços
# ------------------------------------------------------------------ #
@admin_bp.route("/conteudo/servicos", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def services_manage():
    form = ServiceForm()
    if form.validate_on_submit():
        service = Service(
            tenant_id=g.tenant_id,
            title=form.title.data,
            description=form.description.data,
            display_order=_next_display_order(Service),
            is_active=form.is_active.data,
        )
        _attach_image(form.image, service, "image_path", "content/services", remove_field=form.remove_image)
        db.session.add(service)
        log_action("service.created", entity_type="Service", description=service.title)
        db.session.commit()
        flash("Serviço adicionado.", "success")
        return redirect(url_for("admin.services_manage"))

    items = Service.query.order_by(Service.display_order).all()
    return render_template("admin/content_services.html", form=form, items=items, editing=None)


@admin_bp.route("/conteudo/servicos/<int:item_id>/editar", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def service_edit(item_id):
    item = Service.query.filter_by(id=item_id).first_or_404()
    form = ServiceForm(obj=item) if request.method == "GET" else ServiceForm()

    if form.validate_on_submit():
        item.title = form.title.data
        item.description = form.description.data
        item.is_active = form.is_active.data
        _attach_image(form.image, item, "image_path", "content/services", remove_field=form.remove_image)
        log_action("service.updated", entity_type="Service", entity_id=item.id, description=item.title)
        db.session.commit()
        flash("Serviço atualizado com sucesso.", "success")
        return redirect(url_for("admin.services_manage"))

    items = Service.query.order_by(Service.display_order).all()
    return render_template("admin/content_services.html", form=form, items=items, editing=item)


@admin_bp.route("/conteudo/servicos/<int:item_id>/excluir", methods=["POST"])
@roles_required(*EDIT_ROLES)
def service_delete(item_id):
    item = Service.query.filter_by(id=item_id).first_or_404()
    delete_upload(item.image_path)
    log_action("service.deleted", entity_type="Service", entity_id=item.id, description=item.title)
    db.session.delete(item)
    db.session.commit()
    flash("Serviço removido.", "info")
    return redirect(url_for("admin.services_manage"))


# ------------------------------------------------------------------ #
# Conteúdo do site: Galeria
# ------------------------------------------------------------------ #
@admin_bp.route("/conteudo/galeria", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def gallery_manage():
    form = GalleryItemForm()
    if form.validate_on_submit():
        if form.is_featured.data and _featured_gallery_count() >= GalleryItem.MAX_FEATURED:
            flash(
                f"Você já tem {GalleryItem.MAX_FEATURED} pontos destacados. Remova o destaque de um deles antes de destacar outro.",
                "danger",
            )
        else:
            item = GalleryItem(
                tenant_id=g.tenant_id,
                title=form.title.data,
                category=form.category.data,
                display_order=_next_display_order(GalleryItem),
                is_active=form.is_active.data,
                is_featured=form.is_featured.data,
            )
            _apply_gallery_detail_fields(form, item)
            _attach_image(form.image, item, "image_path", "content/gallery", remove_field=form.remove_image)
            db.session.add(item)
            log_action("gallery.created", entity_type="GalleryItem", description=item.title)
            db.session.commit()
            flash("Item de galeria adicionado.", "success")
            return redirect(url_for("admin.gallery_manage"))

    items = GalleryItem.query.order_by(GalleryItem.display_order).all()
    return render_template(
        "admin/content_gallery.html",
        form=form,
        items=items,
        editing=None,
        max_featured=GalleryItem.MAX_FEATURED,
        recommendation_prototype=_gallery_recommendation_prototype(),
    )


@admin_bp.route("/conteudo/galeria/<int:item_id>/editar", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def gallery_edit(item_id):
    item = GalleryItem.query.filter_by(id=item_id).first_or_404()
    form = GalleryItemForm(obj=item) if request.method == "GET" else GalleryItemForm()

    if form.validate_on_submit():
        newly_featured = form.is_featured.data and not item.is_featured
        if newly_featured and _featured_gallery_count() >= GalleryItem.MAX_FEATURED:
            flash(
                f"Você já tem {GalleryItem.MAX_FEATURED} pontos destacados. Remova o destaque de um deles antes de destacar outro.",
                "danger",
            )
        else:
            item.title = form.title.data
            item.category = form.category.data
            item.is_active = form.is_active.data
            item.is_featured = form.is_featured.data
            _apply_gallery_detail_fields(form, item)
            _attach_image(form.image, item, "image_path", "content/gallery", remove_field=form.remove_image)
            log_action("gallery.updated", entity_type="GalleryItem", entity_id=item.id, description=item.title)
            db.session.commit()
            flash("Item de galeria atualizado com sucesso.", "success")
            return redirect(url_for("admin.gallery_manage"))

    items = GalleryItem.query.order_by(GalleryItem.display_order).all()
    return render_template(
        "admin/content_gallery.html",
        form=form,
        items=items,
        editing=item,
        max_featured=GalleryItem.MAX_FEATURED,
        recommendation_prototype=_gallery_recommendation_prototype(),
    )


@admin_bp.route("/conteudo/galeria/<int:item_id>/excluir", methods=["POST"])
@roles_required(*EDIT_ROLES)
def gallery_delete(item_id):
    item = GalleryItem.query.filter_by(id=item_id).first_or_404()
    delete_upload(item.image_path)
    log_action("gallery.deleted", entity_type="GalleryItem", entity_id=item.id, description=item.title)
    db.session.delete(item)
    db.session.commit()
    flash("Item removido.", "info")
    return redirect(url_for("admin.gallery_manage"))


# ------------------------------------------------------------------ #
# Conteúdo do site: Depoimentos e Parceiros
# ------------------------------------------------------------------ #
@admin_bp.route("/conteudo/depoimentos", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def testimonials_manage():
    form = TestimonialForm()
    if form.validate_on_submit():
        item = Testimonial(
            tenant_id=g.tenant_id,
            name=form.name.data,
            company_name=form.company_name.data,
            text=form.text.data,
            display_order=_next_display_order(Testimonial),
            is_active=form.is_active.data,
        )
        db.session.add(item)
        log_action("testimonial.created", entity_type="Testimonial", description=item.name)
        db.session.commit()
        flash("Depoimento adicionado.", "success")
        return redirect(url_for("admin.testimonials_manage"))

    items = Testimonial.query.order_by(Testimonial.display_order).all()
    return render_template("admin/content_testimonials.html", form=form, items=items, editing=None)


@admin_bp.route("/conteudo/depoimentos/<int:item_id>/editar", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def testimonial_edit(item_id):
    item = Testimonial.query.filter_by(id=item_id).first_or_404()
    form = TestimonialForm(obj=item) if request.method == "GET" else TestimonialForm()

    if form.validate_on_submit():
        item.name = form.name.data
        item.company_name = form.company_name.data
        item.text = form.text.data
        item.is_active = form.is_active.data
        log_action("testimonial.updated", entity_type="Testimonial", entity_id=item.id, description=item.name)
        db.session.commit()
        flash("Depoimento atualizado com sucesso.", "success")
        return redirect(url_for("admin.testimonials_manage"))

    items = Testimonial.query.order_by(Testimonial.display_order).all()
    return render_template("admin/content_testimonials.html", form=form, items=items, editing=item)


@admin_bp.route("/conteudo/depoimentos/<int:item_id>/excluir", methods=["POST"])
@roles_required(*EDIT_ROLES)
def testimonial_delete(item_id):
    item = Testimonial.query.filter_by(id=item_id).first_or_404()
    log_action("testimonial.deleted", entity_type="Testimonial", entity_id=item.id, description=item.name)
    db.session.delete(item)
    db.session.commit()
    flash("Depoimento removido.", "info")
    return redirect(url_for("admin.testimonials_manage"))


@admin_bp.route("/conteudo/parceiros", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def partners_manage():
    form = PartnerForm()
    if form.validate_on_submit():
        item = Partner(
            tenant_id=g.tenant_id,
            name=form.name.data,
            display_order=_next_display_order(Partner),
            is_active=form.is_active.data,
        )
        _attach_image(form.logo, item, "logo_path", "content/partners", remove_field=form.remove_logo)
        db.session.add(item)
        log_action("partner.created", entity_type="Partner", description=item.name)
        db.session.commit()
        flash("Parceiro adicionado.", "success")
        return redirect(url_for("admin.partners_manage"))

    items = Partner.query.order_by(Partner.display_order).all()
    return render_template("admin/content_partners.html", form=form, items=items, editing=None)


@admin_bp.route("/conteudo/parceiros/<int:item_id>/editar", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def partner_edit(item_id):
    item = Partner.query.filter_by(id=item_id).first_or_404()
    form = PartnerForm(obj=item) if request.method == "GET" else PartnerForm()

    if form.validate_on_submit():
        item.name = form.name.data
        item.is_active = form.is_active.data
        _attach_image(form.logo, item, "logo_path", "content/partners", remove_field=form.remove_logo)
        log_action("partner.updated", entity_type="Partner", entity_id=item.id, description=item.name)
        db.session.commit()
        flash("Parceiro atualizado com sucesso.", "success")
        return redirect(url_for("admin.partners_manage"))

    items = Partner.query.order_by(Partner.display_order).all()
    return render_template("admin/content_partners.html", form=form, items=items, editing=item)


@admin_bp.route("/conteudo/parceiros/<int:item_id>/excluir", methods=["POST"])
@roles_required(*EDIT_ROLES)
def partner_delete(item_id):
    item = Partner.query.filter_by(id=item_id).first_or_404()
    delete_upload(item.logo_path)
    log_action("partner.deleted", entity_type="Partner", entity_id=item.id, description=item.name)
    db.session.delete(item)
    db.session.commit()
    flash("Parceiro removido.", "info")
    return redirect(url_for("admin.partners_manage"))


# ------------------------------------------------------------------ #
# Conteúdo do site: Seções personalizadas (criadas livremente pelo admin)
# ------------------------------------------------------------------ #
@admin_bp.route("/conteudo/secoes", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def custom_sections_manage():
    form = CustomSectionForm()
    if form.validate_on_submit():
        section = CustomSection(
            tenant_id=g.tenant_id,
            nav_label=form.nav_label.data,
            heading=form.heading.data,
            subtitle=form.subtitle.data,
            slug=_unique_section_slug(form.nav_label.data),
            display_order=_next_display_order(CustomSection),
            is_active=form.is_active.data,
        )
        db.session.add(section)
        log_action("custom_section.created", entity_type="CustomSection", description=section.nav_label)
        db.session.commit()
        flash("Seção criada. Agora adicione os cartões dela.", "success")
        return redirect(url_for("admin.custom_section_items_manage", section_id=section.id))

    sections = CustomSection.query.order_by(CustomSection.display_order).all()
    return render_template("admin/content_custom_sections.html", form=form, sections=sections, editing=None)


@admin_bp.route("/conteudo/secoes/<int:section_id>/editar", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def custom_section_edit(section_id):
    section = CustomSection.query.filter_by(id=section_id).first_or_404()
    form = CustomSectionForm(obj=section) if request.method == "GET" else CustomSectionForm()

    if form.validate_on_submit():
        # O slug só é regerado se o nome no menu mudou de fato — evita que
        # links já compartilhados (#slug-antigo) quebrem só por causa de um
        # ajuste de maiúscula/espaço no rótulo.
        if form.nav_label.data.strip() != section.nav_label:
            section.slug = _unique_section_slug(form.nav_label.data, exclude_id=section.id)
        section.nav_label = form.nav_label.data
        section.heading = form.heading.data
        section.subtitle = form.subtitle.data
        section.is_active = form.is_active.data
        log_action("custom_section.updated", entity_type="CustomSection", entity_id=section.id, description=section.nav_label)
        db.session.commit()
        flash("Seção atualizada com sucesso.", "success")
        return redirect(url_for("admin.custom_sections_manage"))

    sections = CustomSection.query.order_by(CustomSection.display_order).all()
    return render_template("admin/content_custom_sections.html", form=form, sections=sections, editing=section)


@admin_bp.route("/conteudo/secoes/<int:section_id>/excluir", methods=["POST"])
@roles_required(*EDIT_ROLES)
def custom_section_delete(section_id):
    section = CustomSection.query.filter_by(id=section_id).first_or_404()
    # Remove os arquivos de imagem dos cartões antes de excluir a seção —
    # o cascade do banco apaga as linhas, mas não os arquivos no disco.
    for item in section.items:
        delete_upload(item.image_path)
    log_action("custom_section.deleted", entity_type="CustomSection", entity_id=section.id, description=section.nav_label)
    db.session.delete(section)
    db.session.commit()
    flash("Seção removida.", "info")
    return redirect(url_for("admin.custom_sections_manage"))


@admin_bp.route("/conteudo/secoes/reordenar", methods=["POST"])
@roles_required(*EDIT_ROLES)
def custom_sections_reorder():
    return _reorder_items(CustomSection, "custom_section")


@admin_bp.route("/conteudo/secoes/<int:section_id>/itens", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def custom_section_items_manage(section_id):
    section = CustomSection.query.filter_by(id=section_id).first_or_404()
    form = CustomSectionItemForm()
    if form.validate_on_submit():
        item = CustomSectionItem(
            tenant_id=g.tenant_id,
            section_id=section.id,
            title=form.title.data,
            description=form.description.data,
            display_order=_next_display_order_scoped(CustomSectionItem, section_id=section.id),
            is_active=form.is_active.data,
        )
        _attach_image(form.image, item, "image_path", "content/custom_sections", remove_field=form.remove_image)
        db.session.add(item)
        log_action("custom_section_item.created", entity_type="CustomSectionItem", description=item.title)
        db.session.commit()
        flash("Cartão adicionado.", "success")
        return redirect(url_for("admin.custom_section_items_manage", section_id=section.id))

    items = CustomSectionItem.query.filter_by(section_id=section.id).order_by(CustomSectionItem.display_order).all()
    return render_template(
        "admin/content_custom_section_items.html", form=form, section=section, items=items, editing=None
    )


@admin_bp.route("/conteudo/secoes/<int:section_id>/itens/<int:item_id>/editar", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def custom_section_item_edit(section_id, item_id):
    section = CustomSection.query.filter_by(id=section_id).first_or_404()
    item = CustomSectionItem.query.filter_by(id=item_id, section_id=section.id).first_or_404()
    form = CustomSectionItemForm(obj=item) if request.method == "GET" else CustomSectionItemForm()

    if form.validate_on_submit():
        item.title = form.title.data
        item.description = form.description.data
        item.is_active = form.is_active.data
        _attach_image(form.image, item, "image_path", "content/custom_sections", remove_field=form.remove_image)
        log_action("custom_section_item.updated", entity_type="CustomSectionItem", entity_id=item.id, description=item.title)
        db.session.commit()
        flash("Cartão atualizado com sucesso.", "success")
        return redirect(url_for("admin.custom_section_items_manage", section_id=section.id))

    items = CustomSectionItem.query.filter_by(section_id=section.id).order_by(CustomSectionItem.display_order).all()
    return render_template(
        "admin/content_custom_section_items.html", form=form, section=section, items=items, editing=item
    )


@admin_bp.route("/conteudo/secoes/<int:section_id>/itens/<int:item_id>/excluir", methods=["POST"])
@roles_required(*EDIT_ROLES)
def custom_section_item_delete(section_id, item_id):
    section = CustomSection.query.filter_by(id=section_id).first_or_404()
    item = CustomSectionItem.query.filter_by(id=item_id, section_id=section.id).first_or_404()
    delete_upload(item.image_path)
    log_action("custom_section_item.deleted", entity_type="CustomSectionItem", entity_id=item.id, description=item.title)
    db.session.delete(item)
    db.session.commit()
    flash("Cartão removido.", "info")
    return redirect(url_for("admin.custom_section_items_manage", section_id=section.id))


@admin_bp.route("/conteudo/secoes/<int:section_id>/itens/reordenar", methods=["POST"])
@roles_required(*EDIT_ROLES)
def custom_section_items_reorder(section_id):
    # Escopado a UMA seção: diferente de _reorder_items (usado pelas
    # listas globais de Vantagens/Galeria/etc.), os cartões de seções
    # personalizadas são divididos entre várias seções — reordenar os de
    # uma não pode mexer nos de outra.
    CustomSection.query.filter_by(id=section_id).first_or_404()
    payload = request.get_json(silent=True) or {}
    order = payload.get("order")
    if not isinstance(order, list) or not order:
        return jsonify(success=False, message="Lista de ordenação inválida."), 400

    try:
        ordered_ids = [int(raw_id) for raw_id in order]
    except (TypeError, ValueError):
        return jsonify(success=False, message="IDs inválidos."), 400

    items_by_id = {
        item.id: item
        for item in CustomSectionItem.query.filter(
            CustomSectionItem.id.in_(ordered_ids), CustomSectionItem.section_id == section_id
        ).all()
    }
    existing_ids = {
        row.id
        for row in CustomSectionItem.query.filter_by(section_id=section_id).with_entities(CustomSectionItem.id).all()
    }

    if set(ordered_ids) != existing_ids or len(ordered_ids) != len(items_by_id):
        return (
            jsonify(
                success=False,
                message="A lista está desatualizada (um cartão pode ter sido criado/removido por outro usuário). Recarregue a página e tente novamente.",
            ),
            409,
        )

    for position, item_id in enumerate(ordered_ids):
        items_by_id[item_id].display_order = position

    try:
        log_action(
            "custom_section_item.reordered",
            entity_type="CustomSectionItem",
            description=f"Seção {section_id}: nova ordem {ordered_ids}",
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Erro ao reordenar CustomSectionItem")
        return jsonify(success=False, message="Erro ao salvar a nova ordem."), 500

    return jsonify(success=True)


# ------------------------------------------------------------------ #
# Reordenação dos cards (arrastar e soltar)
# ------------------------------------------------------------------ #
# Antes, a única forma de mudar a posição de um item era editá-lo e digitar
# manualmente um número em "Ordem" — fácil de errar (dois itens com o mesmo
# número, por exemplo) e nada intuitivo. Esses endpoints recebem a nova
# ordem completa (lista de IDs, na ordem em que os cards ficaram após o
# arrastar-e-soltar no navegador) e persistem de uma vez só.
@admin_bp.route("/conteudo/servicos/reordenar", methods=["POST"])
@roles_required(*EDIT_ROLES)
def services_reorder():
    return _reorder_items(Service, "service")


@admin_bp.route("/conteudo/galeria/reordenar", methods=["POST"])
@roles_required(*EDIT_ROLES)
def gallery_reorder():
    return _reorder_items(GalleryItem, "gallery")


@admin_bp.route("/conteudo/depoimentos/reordenar", methods=["POST"])
@roles_required(*EDIT_ROLES)
def testimonials_reorder():
    return _reorder_items(Testimonial, "testimonial")


@admin_bp.route("/conteudo/parceiros/reordenar", methods=["POST"])
@roles_required(*EDIT_ROLES)
def partners_reorder():
    return _reorder_items(Partner, "partner")


# Cada grupo da tela de Configurações salva de forma independente (form e
# botão Salvar próprios na gaveta lateral -- ver SETTINGS_GROUPS em
# blueprints/admin/forms.py e templates/admin/settings.html). Uma função de
# aplicação por grupo, só grava os campos daquele grupo especificamente.
def _apply_settings_company(form, settings):
    settings.company_name = form.company_name.data
    settings.company_description = form.company_description.data
    settings.company_whatsapp = form.company_whatsapp.data
    settings.whatsapp_default_message = (form.whatsapp_default_message.data or "").strip() or None
    settings.company_email = form.company_email.data
    settings.company_phone = form.company_phone.data
    settings.company_address = form.company_address.data


def _apply_settings_brand(form, settings):
    if form.remove_favicon.data and settings.favicon_path:
        delete_upload(settings.favicon_path)
        settings.favicon_path = None
    if form.remove_logo.data and settings.logo_path:
        delete_upload(settings.logo_path)
        settings.logo_path = None
    if form.favicon.data:
        old_favicon = settings.favicon_path
        settings.favicon_path = save_favicon(form.favicon.data)
        delete_upload(old_favicon)
    if form.logo.data:
        old_logo = settings.logo_path
        settings.logo_path = save_image(form.logo.data, subfolder="brand/logo")
        delete_upload(old_logo)


def _apply_settings_hero(form, settings):
    settings.hero_title = form.hero_title.data
    settings.hero_subtitle = form.hero_subtitle.data
    settings.hero_media_type = form.hero_media_type.data
    if form.hero_overlay_opacity.data is not None:
        settings.hero_overlay_opacity = form.hero_overlay_opacity.data
    settings.hero_cta_primary_label = form.hero_cta_primary_label.data
    settings.hero_cta_secondary_label = form.hero_cta_secondary_label.data

    settings.services_heading = form.services_heading.data
    settings.services_subtitle = form.services_subtitle.data
    settings.gallery_heading = form.gallery_heading.data
    settings.gallery_subtitle = form.gallery_subtitle.data
    settings.testimonials_heading = form.testimonials_heading.data
    settings.contact_heading = form.contact_heading.data

    settings.services_nav_label = form.services_nav_label.data
    settings.gallery_nav_label = form.gallery_nav_label.data
    settings.testimonials_nav_label = form.testimonials_nav_label.data

    if form.remove_hero_video.data and settings.hero_video_path:
        delete_upload(settings.hero_video_path)
        settings.hero_video_path = None
    if form.remove_hero_image.data and settings.hero_image_path:
        delete_upload(settings.hero_image_path)
        settings.hero_image_path = None
    if form.hero_video.data:
        old_video = settings.hero_video_path
        settings.hero_video_path = save_video(form.hero_video.data)
        delete_upload(old_video)
    if form.hero_image.data:
        old_image = settings.hero_image_path
        settings.hero_image_path = save_image(form.hero_image.data, subfolder="hero")
        delete_upload(old_image)


def _apply_settings_appearance(form, settings):
    settings.theme = form.theme.data
    settings.color_primary = form.color_primary.data
    settings.color_secondary = form.color_secondary.data
    settings.whatsapp_button_color = form.whatsapp_button_color.data
    settings.services_accent_color = form.services_accent_color.data
    settings.gallery_accent_color = form.gallery_accent_color.data
    settings.testimonials_accent_color = form.testimonials_accent_color.data
    settings.card_background_color = form.card_background_color.data
    if form.card_border_radius.data is not None:
        settings.card_border_radius = form.card_border_radius.data


def _apply_settings_legal(form, settings):
    settings.privacy_content = normalize_newlines(form.privacy_content.data)
    settings.terms_content = normalize_newlines(form.terms_content.data)


_SETTINGS_GROUP_APPLIERS = {
    "empresa": _apply_settings_company,
    "marca": _apply_settings_brand,
    "hero": _apply_settings_hero,
    "aparencia": _apply_settings_appearance,
    "legal": _apply_settings_legal,
}


# ------------------------------------------------------------------ #
# Configurações do site (Hero + Empresa + Cores)
# ------------------------------------------------------------------ #
@admin_bp.route("/configuracoes", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def settings_manage():
    settings = SiteSettings.get_solo()

    # Um form por grupo -- em GET, todos partem dos valores atuais salvos.
    # O grupo enviado no POST (se houver) substitui o seu abaixo, mantendo
    # o que a pessoa digitou (inclusive se a validação falhar).
    forms = {group: cls(obj=settings) for group, cls in SETTINGS_GROUPS.items()}
    open_group = request.args.get("aberto") if request.args.get("aberto") in SETTINGS_GROUPS else None

    if request.method == "POST":
        group = request.form.get("group")
        FormClass = SETTINGS_GROUPS.get(group)
        if FormClass is None:
            abort(400)

        form = FormClass()
        forms[group] = form
        open_group = group

        if form.version_id.data is not None and form.version_id.data != settings.version_id:
            flash("As configurações foram alteradas por outro usuário. Recarregue e tente novamente.", "warning")
            return redirect(url_for("admin.settings_manage"))

        if form.validate_on_submit():
            try:
                _SETTINGS_GROUP_APPLIERS[group](form, settings)
            except UploadError as exc:
                flash(str(exc), "danger")
                return render_template("admin/settings.html", forms=forms, settings=settings, open_group=open_group)

            try:
                log_action("settings.updated", entity_type="SiteSettings", entity_id=settings.id, description=group)
                db.session.commit()
                flash("Configurações salvas com sucesso.", "success")
            except StaleDataError:
                db.session.rollback()
                flash("Conflito de edição detectado. Tente novamente.", "warning")
            return redirect(url_for("admin.settings_manage", aberto=group))
        else:
            flash("Não foi possível salvar: verifique os campos destacados.", "danger")

    return render_template("admin/settings.html", forms=forms, settings=settings, open_group=open_group)


# ------------------------------------------------------------------ #
# Usuários (somente Admin)
# ------------------------------------------------------------------ #
@admin_bp.route("/usuarios", methods=["GET", "POST"])
@admin_required
def users_manage():
    form = UserForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash("Já existe um usuário com este e-mail.", "danger")
        elif not form.password.data:
            flash("Senha é obrigatória para novos usuários.", "danger")
        else:
            user = User(
                name=form.name.data,
                email=form.email.data.lower(),
                role=UserRole(form.role.data),
                is_active_flag=form.is_active.data,
                tenant_id=current_user.tenant_id,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            log_action("user.created", entity_type="User", description=user.email)
            db.session.commit()
            flash("Usuário criado com sucesso.", "success")
            return redirect(url_for("admin.users_manage"))

    # User não herda TenantScopedMixin (o e-mail é único globalmente e o
    # super admin não pertence a nenhum tenant) -- por isso o filtro por
    # tenant_id aqui é manual, e é indispensável: sem ele, esta listagem
    # (e a exclusão abaixo) exporia/permitiria apagar usuários de QUALQUER
    # página, inclusive o super admin.
    users = User.query.filter_by(tenant_id=current_user.tenant_id).order_by(User.created_at).all()
    return render_template("admin/users.html", form=form, users=users)


@admin_bp.route("/usuarios/<int:user_id>/editar", methods=["GET", "POST"])
@admin_required
def user_edit(user_id):
    # Mesmo filtro manual explicado em users_manage() -- indispensável pra
    # não editar usuário de outra página (ou o super admin) só sabendo o id.
    user = User.query.filter_by(id=user_id, tenant_id=current_user.tenant_id).first_or_404()
    is_self = user.id == current_user.id

    if request.method == "GET":
        form = UserForm(obj=user, password="")
        form.role.data = user.role.value
    else:
        form = UserForm()

    if form.validate_on_submit():
        existing = User.query.filter_by(email=form.email.data.lower()).first()
        if existing and existing.id != user.id:
            flash("Já existe um usuário com este e-mail.", "danger")
        else:
            # Editando o próprio usuário, papel e status ficam travados aqui
            # (mesmo que o formulário receba outro valor) -- evita que a
            # pessoa se rebaixe/desative por engano e fique trancada fora do
            # próprio painel. Pra isso, é preciso pedir a outro admin.
            if not is_self:
                user.role = UserRole(form.role.data)
                user.is_active_flag = form.is_active.data
            user.name = form.name.data
            user.email = form.email.data.lower()
            if form.password.data:
                user.set_password(form.password.data)
            log_action("user.updated", entity_type="User", entity_id=user.id, description=user.email)
            db.session.commit()
            flash("Usuário atualizado com sucesso.", "success")
            return redirect(url_for("admin.users_manage"))

    users = User.query.filter_by(tenant_id=current_user.tenant_id).order_by(User.created_at).all()
    return render_template("admin/users.html", form=form, users=users, editing=user)


@admin_bp.route("/usuarios/<int:user_id>/excluir", methods=["POST"])
@admin_required
def user_delete(user_id):
    if user_id == current_user.id:
        flash("Você não pode excluir seu próprio usuário.", "danger")
        return redirect(url_for("admin.users_manage"))
    # Ver comentário em users_manage(): filtro por tenant_id manual e
    # obrigatório aqui -- sem ele, um admin poderia excluir usuários de
    # outra página (ou o próprio super admin) só sabendo/adivinhando o id.
    user = User.query.filter_by(id=user_id, tenant_id=current_user.tenant_id).first_or_404()
    log_action("user.deleted", entity_type="User", entity_id=user.id, description=user.email)
    db.session.delete(user)
    db.session.commit()
    flash("Usuário removido.", "info")
    return redirect(url_for("admin.users_manage"))


# ------------------------------------------------------------------ #
# Assinatura (faturas lançadas pelo super admin) -- só leitura, o admin
# da página não edita nada aqui, só acompanha.
# ------------------------------------------------------------------ #
@admin_bp.route("/assinatura")
@admin_required
def subscription():
    invoices = (
        Invoice.query.filter_by(tenant_id=current_user.tenant_id).order_by(Invoice.due_date.desc()).all()
    )
    return render_template("admin/subscription.html", invoices=invoices)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #
def _next_display_order(model):
    """Calcula a próxima posição livre (final da lista) para um novo item.

    Itens novos não pedem mais um número de "ordem" no formulário — entram
    automaticamente no fim da lista e o usuário reordena depois arrastando
    os cards, se quiser mudar a posição.
    """
    max_order = db.session.query(db.func.max(model.display_order)).scalar()
    return 0 if max_order is None else max_order + 1


def _featured_gallery_count() -> int:
    return GalleryItem.query.filter_by(is_featured=True).count()


def _gallery_recommendation_prototype():
    """Formulário 'molde', usado só para desenhar o HTML de uma linha vazia
    de recomendação dentro do <template> (ver content_gallery.html) -- o JS
    clona esse HTML e troca "__INDEX__" pela próxima posição da lista ao
    clicar em "+ Adicionar recomendação". Nunca é validado/submetido."""
    return GalleryRecommendationForm(formdata=None, prefix="recommendations-__INDEX__-")


def _apply_gallery_detail_fields(form, item):
    item.has_detail_page = form.has_detail_page.data
    item.detail_description = (form.detail_description.data or "").strip() or None
    item.detail_monthly_reach = (form.detail_monthly_reach.data or "").strip() or None
    item.detail_retention_value = form.detail_retention_value.data
    item.detail_retention_unit = form.detail_retention_unit.data or "min"
    item.detail_visibility_percent = form.detail_visibility_percent.data
    item.detail_cta_message = (form.detail_cta_message.data or "").strip() or None

    # Reatribuir a coleção inteira (em vez de tentar sincronizar item a
    # item) é mais simples e continua correto: o cascade="all,
    # delete-orphan" do relacionamento cuida de apagar as recomendações
    # antigas que não estão mais na lista nova.
    new_recommendations = []
    order = 0
    for entry in form.recommendations.data:
        label = (entry.get("label") or "").strip()
        if not label:
            continue
        icon = (entry.get("icon") or "").strip() or None
        new_recommendations.append(
            GalleryRecommendation(tenant_id=item.tenant_id, icon=icon, label=label, display_order=order)
        )
        order += 1
    item.recommendations = new_recommendations


def _next_display_order_scoped(model, **filters):
    """Mesma ideia de _next_display_order, mas dentro de um subconjunto
    (ex.: só os cartões de UMA seção personalizada), não da tabela inteira.
    """
    max_order = db.session.query(db.func.max(model.display_order)).filter_by(**filters).scalar()
    return 0 if max_order is None else max_order + 1


def _slugify(text: str) -> str:
    """Converte um texto livre num slug seguro pra usar como #âncora HTML."""
    text = (text or "").strip().lower()
    # Troca qualquer sequência de caracteres não alfanuméricos por um único
    # hífen — cobre acentos, espaços, pontuação etc. (não tentamos
    # transliterar acentos individualmente; o resultado só perde esses
    # caracteres, o que é aceitável para um id interno de âncora).
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "secao"


def _unique_section_slug(nav_label: str, exclude_id: int | None = None) -> str:
    """
    Gera um slug único (e nunca igual às âncoras fixas do site) a partir
    do nome no menu. Se já existir um igual (de outra seção, ou colidindo
    com uma âncora reservada), acrescenta um sufixo numérico crescente
    até achar um livre — nunca falha silenciosamente nem levanta erro de
    unicidade no banco por causa de dois admins criando seções com nomes
    parecidos ao mesmo tempo.
    """
    base = _slugify(nav_label)
    if base in RESERVED_SLUGS:
        base = f"secao-{base}"

    slug = base
    suffix = 2
    while True:
        query = CustomSection.query.filter_by(slug=slug)
        if exclude_id is not None:
            query = query.filter(CustomSection.id != exclude_id)
        if query.first() is None:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1


def _reorder_items(model, log_prefix):
    """
    Persiste a nova ordem dos cards após um arrastar-e-soltar no navegador.

    Espera um corpo JSON `{"order": [id1, id2, ...]}` com TODOS os IDs do
    tipo, na nova ordem desejada — o índice de cada ID na lista vira seu
    `display_order`. Validamos que a lista bate exatamente com os itens
    existentes no banco antes de aplicar qualquer mudança, para não corromper
    a ordenação se o navegador enviar uma lista desatualizada/incompleta
    (ex.: um item foi excluído por outro usuário entre carregar a página e
    arrastar um card).
    """
    payload = request.get_json(silent=True) or {}
    order = payload.get("order")
    if not isinstance(order, list) or not order:
        return jsonify(success=False, message="Lista de ordenação inválida."), 400

    try:
        ordered_ids = [int(raw_id) for raw_id in order]
    except (TypeError, ValueError):
        return jsonify(success=False, message="IDs inválidos."), 400

    items_by_id = {item.id: item for item in model.query.filter(model.id.in_(ordered_ids)).all()}
    existing_ids = {row.id for row in model.query.with_entities(model.id).all()}

    if set(ordered_ids) != existing_ids or len(ordered_ids) != len(items_by_id):
        return (
            jsonify(
                success=False,
                message="A lista está desatualizada (um item pode ter sido criado/removido por outro usuário). Recarregue a página e tente novamente.",
            ),
            409,
        )

    for position, item_id in enumerate(ordered_ids):
        items_by_id[item_id].display_order = position

    try:
        log_action(f"{log_prefix}.reordered", entity_type=model.__name__, description=f"Nova ordem: {ordered_ids}")
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Erro ao reordenar %s", model.__name__)
        return jsonify(success=False, message="Erro ao salvar a nova ordem."), 500

    return jsonify(success=True)


def _attach_image(file_field, model_instance, attribute_name, subfolder, remove_field=None):
    """
    Aplica upload/substituição/remoção de uma imagem em um model.

    Antes, esta função só tratava substituição (upload de um novo
    arquivo) — não havia como remover a mídia já cadastrada sem enviar
    outro arquivo no lugar, pois os formulários de Serviços/Galeria/
    Parceiros não tinham um campo de remoção (diferente do Hero/Logo/
    Favicon em Configurações, que já suportavam isso). `remove_field`
    é o BooleanField "remover imagem atual" do formulário, quando
    existir.
    """
    if remove_field is not None and remove_field.data and not file_field.data:
        old_path = getattr(model_instance, attribute_name)
        if old_path:
            delete_upload(old_path)
        setattr(model_instance, attribute_name, None)
        return

    if not file_field.data:
        return
    try:
        old_path = getattr(model_instance, attribute_name)
        new_path = save_image(file_field.data, subfolder=subfolder)
        setattr(model_instance, attribute_name, new_path)
        if old_path:
            delete_upload(old_path)
    except UploadError as exc:
        flash(str(exc), "danger")
