from flask import Blueprint
from flask_login import login_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
@login_required
def require_login():
    """Todas as rotas deste blueprint exigem usuário autenticado."""
    return None


from app.blueprints.admin import routes  # noqa: E402,F401


@admin_bp.context_processor
def inject_sidebar_data():
    from flask_login import current_user

    from app.models import Invoice, InvoiceStatus, Proposal, SiteSettings
    from app.models.proposal import ProposalStatus

    try:
        count = Proposal.query.filter_by(status=ProposalStatus.NOVO).count()
    except Exception:
        count = 0
    try:
        site_settings = SiteSettings.get_solo()
    except Exception:
        site_settings = None
    try:
        has_pending_cutoff = (
            Invoice.query.filter_by(tenant_id=current_user.tenant_id, status=InvoiceStatus.PENDING)
            .filter(Invoice.service_cutoff_at.isnot(None))
            .count()
            > 0
        )
    except Exception:
        has_pending_cutoff = False
    return {
        "new_proposals_count": count,
        "site_settings": site_settings,
        "has_pending_cutoff": has_pending_cutoff,
    }
