"""
Tratamento centralizado de erros.

- Requisições para /api/* sempre recebem JSON padronizado:
    { "error": "<slug>", "message": "<texto amigável>", "details": {...opcional} }
- Demais requisições recebem páginas HTML amigáveis (templates/errors/*.html).
"""
from flask import jsonify, render_template, request
from werkzeug.exceptions import HTTPException


class APIError(Exception):
    """Exceção de negócio que deve virar uma resposta JSON padronizada na API."""

    def __init__(self, message, status_code=400, error="bad_request", details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error = error
        self.details = details or {}

    def to_dict(self):
        payload = {"error": self.error, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


def _wants_json() -> bool:
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


def register_error_handlers(app):
    @app.errorhandler(APIError)
    def handle_api_error(exc: APIError):
        app.logger.warning("APIError: %s (%s)", exc.message, exc.error)
        return jsonify(exc.to_dict()), exc.status_code

    @app.errorhandler(400)
    def bad_request(exc):
        return _error_response(exc, 400, "bad_request", "Requisição inválida.")

    @app.errorhandler(401)
    def unauthorized(exc):
        return _error_response(exc, 401, "unauthorized", "Autenticação necessária.")

    @app.errorhandler(403)
    def forbidden(exc):
        return _error_response(exc, 403, "forbidden", "Você não tem permissão para acessar este recurso.")

    @app.errorhandler(404)
    def not_found(exc):
        return _error_response(exc, 404, "not_found", "Recurso não encontrado.")

    @app.errorhandler(413)
    def payload_too_large(exc):
        return _error_response(exc, 413, "payload_too_large", "Arquivo excede o tamanho máximo permitido.")

    @app.errorhandler(429)
    def rate_limited(exc):
        return _error_response(exc, 429, "rate_limited", "Muitas requisições. Tente novamente em instantes.")

    @app.errorhandler(500)
    def internal_error(exc):
        app.logger.exception("Erro interno não tratado")
        return _error_response(exc, 500, "internal_error", "Erro interno do servidor.")

    @app.errorhandler(Exception)
    def unhandled_exception(exc):
        if isinstance(exc, HTTPException):
            return exc
        app.logger.exception("Exceção não tratada: %s", exc)
        return _error_response(exc, 500, "internal_error", "Erro interno do servidor.")


def _error_response(exc, status_code, slug, default_message):
    message = getattr(exc, "description", None) or default_message
    if _wants_json():
        return jsonify(error=slug, message=message), status_code
    template_map = {
        400: "errors/400.html",
        401: "errors/401.html",
        403: "errors/403.html",
        404: "errors/404.html",
        413: "errors/413.html",
        429: "errors/429.html",
        500: "errors/500.html",
    }
    template = template_map.get(status_code, "errors/500.html")
    return render_template(template, message=message), status_code
