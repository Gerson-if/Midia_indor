from flask import jsonify

from app.blueprints.api.v1 import api_v1_bp
from app.models import GalleryItem, Partner, Service, SiteSettings, Testimonial


@api_v1_bp.route("/content/site", methods=["GET"])
def get_site_content():
    """
    Exposição pública e somente-leitura do conteúdo do site, pensada para
    futuras integrações (ex.: app mobile, painel headless, totens).
    """
    settings = SiteSettings.get_solo()
    data = settings.to_dict()
    data["services"] = [s.to_dict() for s in Service.query.filter_by(is_active=True).order_by(Service.display_order)]
    data["gallery"] = [g.to_dict() for g in GalleryItem.query.filter_by(is_active=True).order_by(GalleryItem.display_order)]
    data["testimonials"] = [
        t.to_dict() for t in Testimonial.query.filter_by(is_active=True).order_by(Testimonial.display_order)
    ]
    data["partners"] = [p.to_dict() for p in Partner.query.filter_by(is_active=True).order_by(Partner.display_order)]
    return jsonify(success=True, data=data)
