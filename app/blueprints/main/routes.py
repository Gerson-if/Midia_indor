from flask import current_app, jsonify, redirect, render_template, request, url_for

from app.blueprints.main import main_bp
from app.blueprints.main.forms import ProposalRequestForm
from app.extensions import db, limiter
from app.models import CustomSection, GalleryItem, Partner, Proposal, Service, SiteSettings, Testimonial
from app.utils.decorators import log_action
from app.utils.errors import APIError


def _active_custom_sections():
    """
    Seções personalizadas visíveis no site: além de a própria seção estar
    marcada como Ativa, ela precisa ter pelo menos um cartão ativo — senão
    apareceria um item no menu levando pra um bloco vazio, o que é pior
    do que simplesmente não mostrar a seção ainda.
    """
    sections = CustomSection.query.filter_by(is_active=True).order_by(CustomSection.display_order).all()
    for section in sections:
        section.active_items = [item for item in section.items if item.is_active]
    return [s for s in sections if s.active_items]


@main_bp.route("/")
def index():
    settings = SiteSettings.get_solo()
    services = Service.query.filter_by(is_active=True).order_by(Service.display_order).all()
    gallery = GalleryItem.query.filter_by(is_active=True).order_by(GalleryItem.display_order).all()
    testimonials = Testimonial.query.filter_by(is_active=True).order_by(Testimonial.display_order).all()
    partners = Partner.query.filter_by(is_active=True).order_by(Partner.display_order).all()
    custom_sections = _active_custom_sections()
    form = ProposalRequestForm()
    # "sent=1" só chega aqui via redirect pós-envio (ver submit_proposal) —
    # nunca é o resultado direto de um POST, então dar F5/reabrir essa URL
    # simplesmente refaz este GET (idempotente), sem reenviar formulário
    # nenhum. Isso substitui o padrão antigo, onde o próprio POST renderizava
    # a página de sucesso e um F5 do visitante reenviava a solicitação.
    proposal_sent = request.args.get("sent") == "1"

    return render_template(
        "index.html",
        settings=settings,
        services=services,
        gallery=gallery,
        testimonials=testimonials,
        partners=partners,
        custom_sections=custom_sections,
        form=form,
        proposal_sent=proposal_sent,
    )


@main_bp.route("/solicitar-proposta", methods=["POST"])
# Limite por IP elevado: várias pessoas atrás do mesmo IP (rede de
# escritório/condomínio/shopping, NAT de operadora móvel) preenchendo o
# formulário publicamente ao mesmo tempo não deve ser tratado como abuso.
# O honeypot (form.confirm_hp) já cobre a maior parte da proteção
# antibot; este limite existe só para conter picos anormais.
@limiter.limit("30 per minute; 300 per hour")
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
        # sem persistir nada, para não revelar a defesa ao spammer. Segue
        # o mesmo redirect do caminho real (ver comentário abaixo), pra
        # continuar indistinguível de uma submissão legítima.
        current_app.logger.info("Submissão de proposta bloqueada por honeypot (IP=%s)", request.remote_addr)
        if wants_json:
            return jsonify(success=True), 201
        return redirect(url_for("main.index", sent="1") + "#contato")

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

    # Redireciona (Post/Redirect/Get) em vez de renderizar a página de
    # sucesso direto na resposta do POST. Antes, dar F5 (ou reabrir a
    # página pelo botão "Voltar" do navegador) reenviava o mesmo POST e
    # criava uma solicitação duplicada no banco a cada recarregamento —
    # o próprio navegador chega a avisar "Reenviar formulário?", mas
    # muita gente confirma sem entender o que isso significa. Com o
    # redirect, a última página no histórico do navegador é um GET
    # comum (/?sent=1#contato), que pode ser recarregado à vontade sem
    # nunca reenviar nada.
    return redirect(url_for("main.index", sent="1") + "#contato")


def _render_index_with_errors(form):
    # Usado só quando a validação falha: renderiza a página de volta com os
    # erros nos campos. O caminho de sucesso não passa mais por aqui (ver
    # comentário no redirect de submit_proposal) — evita repetir o mesmo
    # POST se o visitante der F5 depois de enviar com sucesso.
    settings = SiteSettings.get_solo()
    services = Service.query.filter_by(is_active=True).order_by(Service.display_order).all()
    gallery = GalleryItem.query.filter_by(is_active=True).order_by(GalleryItem.display_order).all()
    testimonials = Testimonial.query.filter_by(is_active=True).order_by(Testimonial.display_order).all()
    partners = Partner.query.filter_by(is_active=True).order_by(Partner.display_order).all()
    custom_sections = _active_custom_sections()
    return render_template(
        "index.html",
        settings=settings,
        services=services,
        gallery=gallery,
        testimonials=testimonials,
        partners=partners,
        custom_sections=custom_sections,
        form=form,
        proposal_sent=False,
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
