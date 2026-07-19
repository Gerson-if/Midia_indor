from datetime import datetime, timezone

from app.extensions import db


class TimestampMixin:
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Service(TimestampMixin, db.Model):
    """Cartões da seção 'Vantagens' da landing page."""

    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(400), nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "image_url": self.image_path,
            "display_order": self.display_order,
            "is_active": self.is_active,
        }


class GalleryItem(TimestampMixin, db.Model):
    """Itens da seção 'Nossos Pontos'."""

    __tablename__ = "gallery_items"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "image_url": self.image_path,
            "display_order": self.display_order,
            "is_active": self.is_active,
        }


class Testimonial(TimestampMixin, db.Model):
    __tablename__ = "testimonials"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    company_name = db.Column(db.String(120), nullable=False)
    text = db.Column(db.String(600), nullable=False)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "company": self.company_name,
            "text": self.text,
            "is_active": self.is_active,
        }


class Partner(TimestampMixin, db.Model):
    __tablename__ = "partners"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    logo_path = db.Column(db.String(255), nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "logo_url": self.logo_path}


class SiteSettings(TimestampMixin, db.Model):
    """
    Configuração singleton (uma única linha, id=1) com os dados editáveis
    do site: hero, dados da empresa, cores do tema.
    """

    __tablename__ = "site_settings"

    id = db.Column(db.Integer, primary_key=True)

    company_name = db.Column(db.String(120), nullable=False, default="Nexo Mídia")
    company_description = db.Column(db.String(400), nullable=True)
    company_whatsapp = db.Column(db.String(20), nullable=False, default="5567999990000")
    company_email = db.Column(db.String(190), nullable=True)
    company_phone = db.Column(db.String(30), nullable=True)
    company_address = db.Column(db.String(255), nullable=True)
    color_primary = db.Column(db.String(9), nullable=False, default="#FFB020")
    color_secondary = db.Column(db.String(9), nullable=False, default="#37D6C7")

    hero_title = db.Column(db.String(200), nullable=True)
    hero_subtitle = db.Column(db.String(400), nullable=True)
    hero_video_path = db.Column(db.String(255), nullable=True)
    hero_overlay_opacity = db.Column(db.Float, nullable=False, default=0.65)
    hero_cta_primary_label = db.Column(db.String(80), nullable=True)
    hero_cta_secondary_label = db.Column(db.String(80), nullable=True)

    version_id = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version_id}

    @classmethod
    def get_solo(cls):
        """Retorna (criando se necessário) a única linha de configuração."""
        instance = db.session.get(cls, 1)
        if instance is None:
            instance = cls(id=1)
            db.session.add(instance)
            db.session.commit()
        return instance

    def to_dict(self):
        return {
            "company": {
                "name": self.company_name,
                "description": self.company_description,
                "whatsapp": self.company_whatsapp,
                "email": self.company_email,
                "phone": self.company_phone,
                "address": self.company_address,
                "colors": {"primary": self.color_primary, "secondary": self.color_secondary},
            },
            "hero": {
                "title": self.hero_title,
                "subtitle": self.hero_subtitle,
                "video_url": self.hero_video_path,
                "overlay_opacity": self.hero_overlay_opacity,
                "cta_primary_label": self.hero_cta_primary_label,
                "cta_secondary_label": self.hero_cta_secondary_label,
            },
        }
