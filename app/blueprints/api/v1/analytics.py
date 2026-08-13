from flask import g, request

from app.blueprints.api.v1 import api_v1_bp
from app.extensions import csrf, db, limiter
from app.models import PageView

# Teto de sanidade: um "tempo na página" maior que isso é claramente um
# valor bugado (aba deixada aberta em segundo plano por horas) e só
# distorceria a média exibida no dashboard, então é descartado.
MAX_DURATION_SECONDS = 6 * 60 * 60


@api_v1_bp.route("/track/duracao", methods=["POST"])
@csrf.exempt  # disparado via navigator.sendBeacon() pelo visitante público, sem sessão autenticada
@limiter.limit("60 per minute")
def track_duration():
    """
    Recebe quanto tempo o visitante ficou numa página (ver
    app/static/js/analytics-track.js). Só atualiza uma PageView que já
    pertence ao tenant resolvido para esta requisição -- impede um payload
    forjado de escrever em visualizações de outra página.
    """
    payload = request.get_json(silent=True) or {}

    page_view_id = payload.get("page_view_id")
    duration = payload.get("duration")
    if not isinstance(page_view_id, int) or not isinstance(duration, int):
        return "", 204

    if duration <= 0 or duration > MAX_DURATION_SECONDS:
        return "", 204

    view = PageView.query.filter_by(id=page_view_id, tenant_id=g.tenant_id).first()
    if view is None:
        return "", 204

    view.duration_seconds = duration
    db.session.commit()
    return "", 204
