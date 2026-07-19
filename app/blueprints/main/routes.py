from flask import current_app, jsonify, render_template, request

from app.blueprints.main import main_bp
from app.blueprints.main.forms import ProposalRequestForm
from app.extensions import db, limiter
from app.models import GalleryItem, Partner, Proposal, Service, SiteSettings, Testimonial
from app.utils.decorators import log_action
from app.utils.errors import APIError


@main_bp.route("/")
def index():
    settings = SiteSettings.get_solo()
    services = Service.query.filter_by(is_active=True).order_by(Service.display_order).all()
    gallery = GalleryItem.query.filter_by(is_active=True).order_by(GalleryItem.display_order).all()
    testimonials = Testimonial.query.filter_by(is_active=True).order_by(Testimonial.display_order).all()
    partners = Partner.query.filter_by(is_active=True).order_by(Partner.display_order).all()
    form = ProposalRequestForm()

    return render_template(
        "index.html",
        settings=settings,
        services=services,
        gallery=gallery,
        testimonials=testimonials,
        partners=partners,
        form=form,
    )


@main_bp.route("/solicitar-proposta", methods=["POST"])
@limiter.limit("5 per minute; 20 per hour")
def submit_proposal():
    """
    Recebe o formulário de contato do site. Aceita tanto submissão HTML
    tradicional (redireciona de volta com flash) quanto AJAX/JSON
    (retorna JSON), facilitando futura evolução para SPA.
    """
    form = ProposalRequestForm()
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json

    if not form.validate_on_submit():
        if wants_json:
            return jsonify(error="validation_error", message="Dados inválidos.", details=form.errors), 422
        # Os erros de validação já ficam disponíveis em form.errors e são
        # exibidos nos campos do formulário renderizado novamente.
        return _render_index_with_errors(form)

    if form.confirm_hp.data:
        # Honeypot preenchido -> provável bot. Responde "sucesso" falso,
        # sem persistir nada, para não revelar a defesa ao spammer.
        current_app.logger.info("Submissão de proposta bloqueada por honeypot (IP=%s)", request.remote_addr)
        if wants_json:
            return jsonify(success=True), 201
        return _render_index_with_errors(form, sent=True)

    proposal = Proposal(
        name=form.name.data.strip(),
        email=form.email.data.strip().lower(),
        phone=form.phone.data.strip(),
        company_name=(form.company_name.data or "").strip() or None,
        segment=(form.segment.data or "").strip() or None,
        preferred_locations=(form.preferred_locations.data or "").strip() or None,
        budget_range=(form.budget_range.data or "").strip() or None,
        message=(form.message.data or "").strip() or None,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", "")[:255],
    )

    try:
        db.session.add(proposal)
        db.session.flush()  # garante o ID/public_ref antes do log de auditoria
        log_action(
            "proposal.created",
            entity_type="Proposal",
            entity_id=proposal.id,
            description=f"Nova solicitação de {proposal.name} ({proposal.email})",
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Falha ao salvar solicitação de proposta")
        raise APIError("Não foi possível registrar sua solicitação. Tente novamente.", status_code=500, error="internal_error")

    current_app.logger.info("Nova proposta recebida: %s (ref=%s)", proposal.email, proposal.public_ref)

    if wants_json:
        return jsonify(success=True, public_ref=proposal.public_ref), 201

    return _render_index_with_errors(ProposalRequestForm(formdata=None), sent=True)


def _render_index_with_errors(form, sent=False):
    settings = SiteSettings.get_solo()
    services = Service.query.filter_by(is_active=True).order_by(Service.display_order).all()
    gallery = GalleryItem.query.filter_by(is_active=True).order_by(GalleryItem.display_order).all()
    testimonials = Testimonial.query.filter_by(is_active=True).order_by(Testimonial.display_order).all()
    partners = Partner.query.filter_by(is_active=True).order_by(Partner.display_order).all()
    return render_template(
        "index.html",
        settings=settings,
        services=services,
        gallery=gallery,
        testimonials=testimonials,
        partners=partners,
        form=form,
        proposal_sent=sent,
    )


@main_bp.route("/privacidade")
def privacidade():
    settings = SiteSettings.get_solo()
    return render_template("privacidade.html", settings=settings)


@main_bp.route("/termos")
def termos():
    settings = SiteSettings.get_solo()
    return render_template("termos.html", settings=settings)


@main_bp.route("/healthz")
def healthz():
    """Endpoint de health check para load balancers / orquestradores."""
    try:
        db.session.execute(db.text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error("Health check falhou: %s", exc)
        db_status = "error"
    status_code = 200 if db_status == "ok" else 503
    return jsonify(status="ok" if db_status == "ok" else "degraded", database=db_status), status_code
