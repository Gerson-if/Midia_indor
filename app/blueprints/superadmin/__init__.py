from flask import Blueprint, abort, redirect, url_for
from flask_login import current_user

superadmin_bp = Blueprint("superadmin", __name__, url_prefix="/super")


@superadmin_bp.before_request
def require_super_admin():
    """Todas as rotas deste blueprint exigem o super admin autenticado,
    exceto a própria tela de login."""
    from flask import request

    if request.endpoint == "superadmin.login":
        return None
    if not current_user.is_authenticated:
        return redirect(url_for("superadmin.login"))
    if not getattr(current_user, "is_super_admin", False):
        abort(403)
    return None


from app.blueprints.superadmin import routes  # noqa: E402,F401
