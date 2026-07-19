from flask import abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.blueprints.admin import admin_bp
from app.blueprints.admin.forms import (
    GalleryItemForm,
    PartnerForm,
    ProposalStatusForm,
    ServiceForm,
    SiteSettingsForm,
    TestimonialForm,
    UserForm,
)
from app.extensions import db
from app.models import AuditLog, GalleryItem, Partner, Proposal, Service, SiteSettings, Testimonial, User, UserRole
from app.models.proposal import ProposalStatus
from app.services.uploads import UploadError, delete_upload, save_image, save_video
from app.services.whatsapp import build_client_whatsapp_link
from app.utils.decorators import admin_required, log_action, roles_required
from sqlalchemy.orm.exc import StaleDataError

STAFF_ROLES = (UserRole.ADMIN, UserRole.EDITOR, UserRole.VIEWER)
EDIT_ROLES = (UserRole.ADMIN, UserRole.EDITOR)


# ------------------------------------------------------------------ #
# Dashboard
# ------------------------------------------------------------------ #
@admin_bp.route("/")
@roles_required(*STAFF_ROLES)
def dashboard():
    total_proposals = Proposal.query.count()
    new_proposals = Proposal.query.filter_by(status=ProposalStatus.NOVO).count()
    converted = Proposal.query.filter_by(status=ProposalStatus.CONVERTIDO).count()
    recent_proposals = Proposal.query.order_by(Proposal.created_at.desc()).limit(6).all()

    return render_template(
        "admin/dashboard.html",
        total_proposals=total_proposals,
        new_proposals=new_proposals,
        converted=converted,
        recent_proposals=recent_proposals,
        active_gallery=GalleryItem.query.filter_by(is_active=True).count(),
        active_partners=Partner.query.filter_by(is_active=True).count(),
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
    proposal = Proposal.query.get_or_404(proposal_id)
    form = ProposalStatusForm(status=proposal.status.value, internal_notes=proposal.internal_notes, version_id=proposal.version_id)
    whatsapp_link = build_client_whatsapp_link(proposal, current_app.config["COMPANY_NAME"])
    history = (
        AuditLog.query.filter_by(entity_type="Proposal", entity_id=str(proposal.id))
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
    proposal = Proposal.query.get_or_404(proposal_id)
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
    proposal = Proposal.query.get_or_404(proposal_id)
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
    proposal = Proposal.query.get_or_404(proposal_id)
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
            title=form.title.data,
            description=form.description.data,
            display_order=form.display_order.data or 0,
            is_active=form.is_active.data,
        )
        _attach_image(form.image, service, "image_path", "content/services")
        db.session.add(service)
        log_action("service.created", entity_type="Service", description=service.title)
        db.session.commit()
        flash("Serviço adicionado.", "success")
        return redirect(url_for("admin.services_manage"))

    items = Service.query.order_by(Service.display_order).all()
    return render_template("admin/content_services.html", form=form, items=items)


@admin_bp.route("/conteudo/servicos/<int:item_id>/excluir", methods=["POST"])
@roles_required(*EDIT_ROLES)
def service_delete(item_id):
    item = Service.query.get_or_404(item_id)
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
        item = GalleryItem(
            title=form.title.data,
            category=form.category.data,
            display_order=form.display_order.data or 0,
            is_active=form.is_active.data,
        )
        _attach_image(form.image, item, "image_path", "content/gallery")
        db.session.add(item)
        log_action("gallery.created", entity_type="GalleryItem", description=item.title)
        db.session.commit()
        flash("Item de galeria adicionado.", "success")
        return redirect(url_for("admin.gallery_manage"))

    items = GalleryItem.query.order_by(GalleryItem.display_order).all()
    return render_template("admin/content_gallery.html", form=form, items=items)


@admin_bp.route("/conteudo/galeria/<int:item_id>/excluir", methods=["POST"])
@roles_required(*EDIT_ROLES)
def gallery_delete(item_id):
    item = GalleryItem.query.get_or_404(item_id)
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
            name=form.name.data,
            company_name=form.company_name.data,
            text=form.text.data,
            display_order=form.display_order.data or 0,
            is_active=form.is_active.data,
        )
        db.session.add(item)
        log_action("testimonial.created", entity_type="Testimonial", description=item.name)
        db.session.commit()
        flash("Depoimento adicionado.", "success")
        return redirect(url_for("admin.testimonials_manage"))

    items = Testimonial.query.order_by(Testimonial.display_order).all()
    return render_template("admin/content_testimonials.html", form=form, items=items)


@admin_bp.route("/conteudo/depoimentos/<int:item_id>/excluir", methods=["POST"])
@roles_required(*EDIT_ROLES)
def testimonial_delete(item_id):
    item = Testimonial.query.get_or_404(item_id)
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
            name=form.name.data,
            display_order=form.display_order.data or 0,
            is_active=form.is_active.data,
        )
        _attach_image(form.logo, item, "logo_path", "content/partners")
        db.session.add(item)
        log_action("partner.created", entity_type="Partner", description=item.name)
        db.session.commit()
        flash("Parceiro adicionado.", "success")
        return redirect(url_for("admin.partners_manage"))

    items = Partner.query.order_by(Partner.display_order).all()
    return render_template("admin/content_partners.html", form=form, items=items)


@admin_bp.route("/conteudo/parceiros/<int:item_id>/excluir", methods=["POST"])
@roles_required(*EDIT_ROLES)
def partner_delete(item_id):
    item = Partner.query.get_or_404(item_id)
    delete_upload(item.logo_path)
    log_action("partner.deleted", entity_type="Partner", entity_id=item.id, description=item.name)
    db.session.delete(item)
    db.session.commit()
    flash("Parceiro removido.", "info")
    return redirect(url_for("admin.partners_manage"))


# ------------------------------------------------------------------ #
# Configurações do site (Hero + Empresa + Cores)
# ------------------------------------------------------------------ #
@admin_bp.route("/configuracoes", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def settings_manage():
    settings = SiteSettings.get_solo()
    form = SiteSettingsForm(obj=settings)

    if request.method == "POST":
        form = SiteSettingsForm()
        if form.version_id.data is not None and form.version_id.data != settings.version_id:
            flash("As configurações foram alteradas por outro usuário. Recarregue e tente novamente.", "warning")
            return redirect(url_for("admin.settings_manage"))

        if form.validate_on_submit():
            settings.company_name = form.company_name.data
            settings.company_description = form.company_description.data
            settings.company_whatsapp = form.company_whatsapp.data
            settings.company_email = form.company_email.data
            settings.company_phone = form.company_phone.data
            settings.company_address = form.company_address.data
            settings.color_primary = form.color_primary.data
            settings.color_secondary = form.color_secondary.data
            settings.hero_title = form.hero_title.data
            settings.hero_subtitle = form.hero_subtitle.data
            if form.hero_overlay_opacity.data is not None:
                settings.hero_overlay_opacity = form.hero_overlay_opacity.data
            settings.hero_cta_primary_label = form.hero_cta_primary_label.data
            settings.hero_cta_secondary_label = form.hero_cta_secondary_label.data

            if form.hero_video.data:
                try:
                    old_video = settings.hero_video_path
                    settings.hero_video_path = save_video(form.hero_video.data)
                    delete_upload(old_video)
                except UploadError as exc:
                    flash(str(exc), "danger")
                    return render_template("admin/settings.html", form=form, settings=settings)

            try:
                log_action("settings.updated", entity_type="SiteSettings", entity_id=settings.id)
                db.session.commit()
                flash("Configurações salvas com sucesso.", "success")
            except StaleDataError:
                db.session.rollback()
                flash("Conflito de edição detectado. Tente novamente.", "warning")
            return redirect(url_for("admin.settings_manage"))

    return render_template("admin/settings.html", form=form, settings=settings)


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
            user = User(name=form.name.data, email=form.email.data.lower(), role=UserRole(form.role.data), is_active_flag=form.is_active.data)
            user.set_password(form.password.data)
            db.session.add(user)
            log_action("user.created", entity_type="User", description=user.email)
            db.session.commit()
            flash("Usuário criado com sucesso.", "success")
            return redirect(url_for("admin.users_manage"))

    users = User.query.order_by(User.created_at).all()
    return render_template("admin/users.html", form=form, users=users)


@admin_bp.route("/usuarios/<int:user_id>/excluir", methods=["POST"])
@admin_required
def user_delete(user_id):
    if user_id == current_user.id:
        flash("Você não pode excluir seu próprio usuário.", "danger")
        return redirect(url_for("admin.users_manage"))
    user = User.query.get_or_404(user_id)
    log_action("user.deleted", entity_type="User", entity_id=user.id, description=user.email)
    db.session.delete(user)
    db.session.commit()
    flash("Usuário removido.", "info")
    return redirect(url_for("admin.users_manage"))


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #
def _attach_image(file_field, model_instance, attribute_name, subfolder):
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
