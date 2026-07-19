import json
from functools import wraps

from flask import abort, jsonify, request
from flask_login import current_user

from app.extensions import db
from app.models import AuditLog


def roles_required(*roles):
    """
    Restringe o acesso a uma rota aos papéis informados.
    Uso: @roles_required(UserRole.ADMIN, UserRole.EDITOR)
    Deve ser aplicado sempre DEPOIS de @login_required.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not current_user.has_role(*roles):
                if request.path.startswith("/api/"):
                    return jsonify(error="forbidden", message="Permissão insuficiente."), 403
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def admin_required(view_func):
    """Atalho para exigir explicitamente o papel de administrador."""
    from app.models import UserRole

    return roles_required(UserRole.ADMIN)(view_func)


def log_action(action: str, entity_type: str = None, entity_id=None, description: str = None, **metadata):
    """
    Registra uma ação no log de auditoria. Não realiza commit por conta
    própria: a operação de negócio principal deve commitar tudo junto,
    garantindo atomicidade (tudo ou nada).
    """
    entry = AuditLog(
        user_id=current_user.id if getattr(current_user, "is_authenticated", False) else None,
        user_email_snapshot=getattr(current_user, "email", None),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        description=description,
        metadata_json=json.dumps(metadata, default=str) if metadata else None,
        ip_address=request.remote_addr if request else None,
        user_agent=request.headers.get("User-Agent", "")[:255] if request else None,
    )
    db.session.add(entry)
    return entry
