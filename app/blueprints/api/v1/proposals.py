from flask import current_app, jsonify, request
from flask_login import current_user, login_required

from app.blueprints.api.v1 import api_v1_bp
from app.extensions import csrf, db, limiter
from app.models import Proposal
from app.models.proposal import ProposalStatus
from app.services.whatsapp import build_client_whatsapp_link
from app.utils.decorators import log_action, roles_required
from app.utils.errors import APIError

STAFF_ROLES = ("admin", "editor", "viewer")


@api_v1_bp.route("/proposals", methods=["POST"])
@csrf.exempt  # endpoint de API pensado para integrações externas (autenticadas por outros meios em produção)
@limiter.limit("5 per minute; 20 per hour")
def create_proposal():
    """
    Cria uma solicitação via API (uso futuro: app mobile, formulários
    externos, integrações com CRM). Mesma validação de negócio do
    formulário público, retornando erros padronizados em JSON.
    """
    payload = request.get_json(silent=True) or {}

    required = ["name", "email", "phone"]
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        raise APIError(
            "Campos obrigatórios ausentes.",
            status_code=422,
            error="validation_error",
            details={"missing_fields": missing},
        )

    proposal = Proposal(
        name=str(payload["name"]).strip()[:150],
        email=str(payload["email"]).strip().lower()[:190],
        phone=str(payload["phone"]).strip()[:30],
        company_name=(payload.get("company_name") or "").strip()[:150] or None,
        segment=(payload.get("segment") or "").strip()[:100] or None,
        preferred_locations=(payload.get("preferred_locations") or "").strip()[:255] or None,
        budget_range=(payload.get("budget_range") or "").strip()[:60] or None,
        message=(payload.get("message") or "").strip()[:2000] or None,
        source=str(payload.get("source", "api"))[:50],
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", "")[:255],
    )

    db.session.add(proposal)
    db.session.flush()
    log_action("proposal.created", entity_type="Proposal", entity_id=proposal.id, description="Criada via API")
    db.session.commit()

    return jsonify(success=True, data=proposal.to_dict()), 201


@api_v1_bp.route("/proposals", methods=["GET"])
@login_required
@roles_required(*STAFF_ROLES)
def list_proposals():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    status = request.args.get("status")

    query = Proposal.query
    if status and status in {s.value for s in ProposalStatus}:
        query = query.filter(Proposal.status == ProposalStatus(status))

    pagination = query.order_by(Proposal.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify(
        success=True,
        data=[p.to_dict() for p in pagination.items],
        pagination={
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        },
    )


@api_v1_bp.route("/proposals/<int:proposal_id>", methods=["GET"])
@login_required
@roles_required(*STAFF_ROLES)
def get_proposal(proposal_id):
    proposal = db.session.get(Proposal, proposal_id)
    if not proposal:
        raise APIError("Solicitação não encontrada.", status_code=404, error="not_found")
    data = proposal.to_dict()
    data["whatsapp_link"] = build_client_whatsapp_link(proposal, current_app.config["COMPANY_NAME"])
    return jsonify(success=True, data=data)


@api_v1_bp.route("/proposals/<int:proposal_id>/status", methods=["PATCH"])
@login_required
@roles_required("admin", "editor")
def update_proposal_status(proposal_id):
    proposal = db.session.get(Proposal, proposal_id)
    if not proposal:
        raise APIError("Solicitação não encontrada.", status_code=404, error="not_found")

    payload = request.get_json(silent=True) or {}
    new_status = payload.get("status")
    if new_status not in {s.value for s in ProposalStatus}:
        raise APIError("Status inválido.", status_code=422, error="validation_error")

    expected_version = payload.get("version_id")
    if expected_version is not None and int(expected_version) != proposal.version_id:
        raise APIError(
            "O registro foi modificado por outro usuário. Recarregue e tente novamente.",
            status_code=409,
            error="conflict",
        )

    old_status = proposal.status
    proposal.status = ProposalStatus(new_status)
    if "internal_notes" in payload:
        proposal.internal_notes = payload["internal_notes"]

    log_action(
        "proposal.status_changed",
        entity_type="Proposal",
        entity_id=proposal.id,
        description=f"{old_status.value} -> {proposal.status.value}",
    )
    db.session.commit()
    return jsonify(success=True, data=proposal.to_dict())
