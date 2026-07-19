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
    from app.models import Proposal
    from app.models.proposal import ProposalStatus

    try:
        count = Proposal.query.filter_by(status=ProposalStatus.NOVO).count()
    except Exception:
        count = 0
    return {"new_proposals_count": count}
