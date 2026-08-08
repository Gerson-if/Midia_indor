"""
Popula o banco de dados com conteúdo inicial de demonstração para uma
página (tenant) específica. Idempotente: pode ser executado múltiplas
vezes sem duplicar registros.

Uso:
    flask seed-demo --tenant-slug=default
"""
from app.extensions import db
from app.models import GalleryItem, Partner, Service, SiteSettings, Testimonial


def run_seed(tenant_id: int):
    settings = SiteSettings.get_solo(tenant_id=tenant_id)
    if not settings.hero_title:
        settings.hero_title = "Sua marca no centro das atenções."
        settings.hero_subtitle = "Telas digitais em pontos estratégicos com conteúdo que muda em tempo real."
        settings.hero_cta_primary_label = "Anuncie Conosco"
        settings.hero_cta_secondary_label = "Conhecer Locais"
        settings.company_description = "Rede de mídia indoor digital estratégica para sua marca."

    if not settings.privacy_content:
        settings.privacy_content = SiteSettings._default_privacy_content()

    if not settings.terms_content:
        settings.terms_content = SiteSettings._default_terms_content()

    if Service.query.filter_by(tenant_id=tenant_id).count() == 0:
        db.session.add_all(
            [
                Service(
                    tenant_id=tenant_id,
                    title="Mídia em Elevadores",
                    description="Telas verticais de alto impacto em prédios comerciais e residenciais.",
                    display_order=1,
                ),
                Service(
                    tenant_id=tenant_id,
                    title="Gestão em Tempo Real",
                    description="Substitua anúncios remotamente, sem custo extra de instalação.",
                    display_order=2,
                ),
                Service(
                    tenant_id=tenant_id,
                    title="Cobertura Premium",
                    description="Selecione bairros e perfis de público por região da cidade.",
                    display_order=3,
                ),
                Service(
                    tenant_id=tenant_id,
                    title="Produção Inclusa",
                    description="Nossa equipe cria ou adapta as artes da sua campanha.",
                    display_order=4,
                ),
            ]
        )

    if GalleryItem.query.filter_by(tenant_id=tenant_id).count() == 0:
        db.session.add_all(
            [
                GalleryItem(tenant_id=tenant_id, title="Torre Horizonte", category="Elevadores", display_order=1),
                GalleryItem(tenant_id=tenant_id, title="Vitalis Centro", category="Academias", display_order=2),
                GalleryItem(
                    tenant_id=tenant_id, title="Bem Estar Diagnósticos", category="Clínicas", display_order=3
                ),
                GalleryItem(
                    tenant_id=tenant_id, title="Alameda Jardins", category="Condomínios", display_order=4
                ),
            ]
        )

    if Testimonial.query.filter_by(tenant_id=tenant_id).count() == 0:
        db.session.add_all(
            [
                Testimonial(
                    tenant_id=tenant_id,
                    name="Marcela Duarte",
                    company_name="Vitalis Academia",
                    text="Aumentamos a procura por planos anuais depois de 2 meses.",
                    display_order=1,
                ),
                Testimonial(
                    tenant_id=tenant_id,
                    name="Rafael Nunes",
                    company_name="Clínica Bem Estar",
                    text="Fácil de trocar a arte quando lançamos uma promoção nova.",
                    display_order=2,
                ),
            ]
        )

    if Partner.query.filter_by(tenant_id=tenant_id).count() == 0:
        db.session.add_all(
            [
                Partner(tenant_id=tenant_id, name="Grupo Horizonte", display_order=1),
                Partner(tenant_id=tenant_id, name="Vitalis Academia", display_order=2),
                Partner(tenant_id=tenant_id, name="Clínica Bem Estar", display_order=3),
                Partner(tenant_id=tenant_id, name="Condomínio Alameda", display_order=4),
            ]
        )

    db.session.commit()
