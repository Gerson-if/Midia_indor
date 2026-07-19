from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api")

from app.blueprints.api.v1 import api_v1_bp  # noqa: E402

api_bp.register_blueprint(api_v1_bp, url_prefix="/v1")
