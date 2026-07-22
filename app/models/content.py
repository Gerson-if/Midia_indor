from datetime import datetime, timezone

from flask import url_for
from sqlalchemy.exc import IntegrityError

from app.extensions import db


def _static_url(relative_path):
    """
    Converte um caminho relativo salvo no banco (ex.: "content/services/x.webp")
    em uma URL absoluta e utilizável fora do servidor da aplicação (apps
    mobile, totens, painéis headless, ou qualquer outro domínio consumindo
    a API pública em /api/v1/content/site).
    """
    if not relative_path:
        return None
    return url_for("static", filename=relative_path, _external=True)


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
            "image_url": _static_url(self.image_path),
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
            "image_url": _static_url(self.image_path),
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
        return {"id": self.id, "name": self.name, "logo_url": _static_url(self.logo_path)}


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

    # ---- Identidade visual (favicon / logo) ----
    favicon_path = db.Column(db.String(255), nullable=True)
    logo_path = db.Column(db.String(255), nullable=True)

    # ---- Hero (topo do site) ----
    hero_title = db.Column(db.String(200), nullable=True)
    hero_subtitle = db.Column(db.String(400), nullable=True)
    # "video" ou "image": define qual mídia é exibida como capa do Hero.
    hero_media_type = db.Column(db.String(10), nullable=False, default="video")
    hero_video_path = db.Column(db.String(255), nullable=True)
    hero_image_path = db.Column(db.String(255), nullable=True)
    hero_overlay_opacity = db.Column(db.Float, nullable=False, default=0.65)
    hero_cta_primary_label = db.Column(db.String(80), nullable=True)
    hero_cta_secondary_label = db.Column(db.String(80), nullable=True)

    # ---- Aparência das demais seções (cards, destaques) ----
    services_accent_color = db.Column(db.String(9), nullable=False, default="#FFB020")
    gallery_accent_color = db.Column(db.String(9), nullable=False, default="#FFB020")
    testimonials_accent_color = db.Column(db.String(9), nullable=False, default="#37D6C7")
    card_background_color = db.Column(db.String(9), nullable=False, default="#131A24")
    card_border_radius = db.Column(db.Integer, nullable=False, default=12)

    # ---- Tema visual do sistema inteiro (site público + painel) ----
    # "dark" (padrão) ou "light". Configurável só pelo admin, em
    # Configurações → Aparência, e vale para todo mundo que acessa o
    # sistema (não é uma preferência por visitante/navegador).
    theme = db.Column(db.String(10), nullable=False, default="dark")

    # ---- Páginas legais (editáveis pelo painel, sem tocar em código) ----
    privacy_content = db.Column(db.Text, nullable=True)
    terms_content = db.Column(db.Text, nullable=True)

    version_id = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version_id}

    @classmethod
    def get_solo(cls):
        """Retorna (criando se necessário) a única linha de configuração."""
        instance = db.session.get(cls, 1)
        if instance is not None:
            return instance

        # Corrida de concorrência: com múltiplos usuários acessando o site
        # ao mesmo tempo (ex.: logo após a instalação, antes de existir a
        # linha de configuração), duas ou mais requisições podem chegar
        # aqui simultaneamente, ambas verem "instance is None" e tentarem
        # criar a linha id=1 ao mesmo tempo. Sem tratamento, a segunda a
        # commitar recebe um IntegrityError (chave primária duplicada) e
        # a requisição falha com erro 500 — exatamente o tipo de falha
        # "só acontece com vários acessos ao mesmo tempo" relatado. Como
        # o SGBD garante que só uma dessas escritas concorrentes vai
        # vencer, tratamos a perdedora simplesmente re-buscando a linha
        # que a vencedora acabou de criar, em vez de propagar o erro.
        instance = cls(
            id=1,
            privacy_content=cls._default_privacy_content(),
            terms_content=cls._default_terms_content(),
        )
        db.session.add(instance)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            instance = db.session.get(cls, 1)
            if instance is None:
                # Situação extremamente improvável (a linha sumiu entre o
                # rollback e esta busca); melhor levantar um erro claro do
                # que devolver None e quebrar os templates que dependem
                # de "settings" sempre existir.
                raise
        return instance

    @staticmethod
    def _default_privacy_content() -> str:
        return (
            "## 1. Dados que coletamos\n"
            "Coletamos informações fornecidas voluntariamente em formulários de contato, "
            "como nome, e-mail, telefone e mensagem, além de dados técnicos de navegação "
            "(endereço IP e navegador) para fins de segurança e estatística.\n\n"
            "## 2. Como usamos seus dados\n"
            "As informações são utilizadas exclusivamente para responder solicitações "
            "comerciais, entrar em contato via WhatsApp, e-mail ou telefone, e melhorar "
            "a experiência de navegação no site.\n\n"
            "## 3. Armazenamento e segurança\n"
            "Seus dados são armazenados em banco de dados protegido, com acesso restrito "
            "à nossa equipe autorizada e trilha de auditoria de todos os acessos "
            "administrativos.\n\n"
            "## 4. Seus direitos\n"
            "Você pode solicitar a qualquer momento a exclusão ou correção dos seus dados "
            "entrando em contato através do nosso e-mail de contato.\n\n"
            "Este texto é um modelo inicial — edite-o em Configurações → Páginas Legais."
        )

    @staticmethod
    def _default_terms_content() -> str:
        return (
            "## 1. Aceitação dos termos\n"
            "Ao utilizar este site, você concorda com os presentes Termos de Uso e com "
            "nossa Política de Privacidade.\n\n"
            "## 2. Uso do site\n"
            "O conteúdo disponibilizado tem caráter informativo e comercial. É proibida "
            "a reprodução total ou parcial sem autorização prévia.\n\n"
            "## 3. Solicitações de proposta\n"
            "Ao enviar o formulário de contato, você nos autoriza a utilizar os dados "
            "informados para fins de retorno comercial.\n\n"
            "Este texto é um modelo inicial — edite-o em Configurações → Páginas Legais."
        )

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
                "favicon_url": _static_url(self.favicon_path),
                "logo_url": _static_url(self.logo_path),
            },
            "hero": {
                "title": self.hero_title,
                "subtitle": self.hero_subtitle,
                "media_type": self.hero_media_type,
                "video_url": _static_url(self.hero_video_path),
                "image_url": _static_url(self.hero_image_path),
                "overlay_opacity": self.hero_overlay_opacity,
                "cta_primary_label": self.hero_cta_primary_label,
                "cta_secondary_label": self.hero_cta_secondary_label,
            },
            "theme": {
                "services_accent": self.services_accent_color,
                "gallery_accent": self.gallery_accent_color,
                "testimonials_accent": self.testimonials_accent_color,
                "card_background": self.card_background_color,
                "card_border_radius": self.card_border_radius,
            },
        }
