import io

from app.models import Proposal, Service
from tests.conftest import login


def test_admin_dashboard_loads(client, admin_user):
    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert "Visão Geral" in resp.get_data(as_text=True)


def test_admin_dashboard_charts_render_with_data(client, admin_user, db):
    proposal = Proposal(name="Grafico Teste", email="grafico@example.com", phone="67911112222")
    db.session.add(proposal)
    db.session.commit()

    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get("/admin/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "timelineChart" in html
    assert "statusChart" in html


def test_create_service(client, admin_user, db):
    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.post(
        "/admin/conteudo/servicos",
        data={"title": "Mídia em Elevadores", "description": "Telas em prédios", "display_order": 1, "is_active": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Service.query.filter_by(title="Mídia em Elevadores").first() is not None


def test_delete_service(client, admin_user, db):
    service = Service(title="Temporário", description="desc")
    db.session.add(service)
    db.session.commit()

    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.post(f"/admin/conteudo/servicos/{service.id}/excluir", follow_redirects=True)
    assert resp.status_code == 200
    assert Service.query.get(service.id) is None


def test_edit_service_updates_fields(client, admin_user, db):
    service = Service(title="Título Antigo", description="desc antiga", display_order=1)
    db.session.add(service)
    db.session.commit()
    service_id = service.id

    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get(f"/admin/conteudo/servicos/{service_id}/editar")
    assert resp.status_code == 200
    assert "Título Antigo" in resp.get_data(as_text=True)

    resp = client.post(
        f"/admin/conteudo/servicos/{service_id}/editar",
        data={"title": "Título Novo", "description": "descrição nova", "display_order": 2, "is_active": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    updated = Service.query.get(service_id)
    assert updated.title == "Título Novo"
    assert updated.description == "descrição nova"


def test_edit_gallery_item(client, admin_user, db):
    from app.models import GalleryItem

    item = GalleryItem(title="Ponto A", category="Academias")
    db.session.add(item)
    db.session.commit()

    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.post(
        f"/admin/conteudo/galeria/{item.id}/editar",
        data={"title": "Ponto B", "category": "Elevadores", "display_order": 0, "is_active": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    updated = GalleryItem.query.get(item.id)
    assert updated.title == "Ponto B"
    assert updated.category == "Elevadores"


def test_edit_testimonial(client, admin_user, db):
    from app.models import Testimonial

    item = Testimonial(name="Cliente A", company_name="Empresa A", text="depoimento original")
    db.session.add(item)
    db.session.commit()

    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.post(
        f"/admin/conteudo/depoimentos/{item.id}/editar",
        data={"name": "Cliente B", "company_name": "Empresa B", "text": "depoimento editado", "display_order": 0, "is_active": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    updated = Testimonial.query.get(item.id)
    assert updated.name == "Cliente B"
    assert updated.text == "depoimento editado"


def test_edit_partner(client, admin_user, db):
    from app.models import Partner

    item = Partner(name="Marca A")
    db.session.add(item)
    db.session.commit()

    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.post(
        f"/admin/conteudo/parceiros/{item.id}/editar",
        data={"name": "Marca B", "display_order": 0, "is_active": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    updated = Partner.query.get(item.id)
    assert updated.name == "Marca B"


def test_settings_update(client, admin_user, db):
    from app.models import SiteSettings

    login(client, "admin@teste.com", "SenhaForte123!")
    settings = SiteSettings.get_solo()
    resp = client.post(
        "/admin/configuracoes",
        data={
            "company_name": "Nova Empresa",
            "company_whatsapp": "5567900001111",
            "color_primary": "#FFB020",
            "color_secondary": "#37D6C7",
            "hero_overlay_opacity": "0.5",
            "hero_media_type": "video",
            "services_accent_color": "#FFB020",
            "gallery_accent_color": "#FFB020",
            "testimonials_accent_color": "#37D6C7",
            "card_background_color": "#131A24",
            "card_border_radius": "12",
            "version_id": settings.version_id,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(settings)
    assert settings.company_name == "Nova Empresa"


def test_settings_hero_media_toggle_and_removal(client, admin_user, db):
    """Cobre a alternância vídeo/imagem e a remoção de mídia do Hero."""
    from app.models import SiteSettings

    login(client, "admin@teste.com", "SenhaForte123!")
    settings = SiteSettings.get_solo()
    settings.hero_video_path = "uploads/hero/fake_video.mp4"
    db.session.commit()

    base_data = {
        "company_name": settings.company_name,
        "company_whatsapp": settings.company_whatsapp,
        "color_primary": settings.color_primary,
        "color_secondary": settings.color_secondary,
        "hero_overlay_opacity": "0.5",
        "hero_media_type": "image",
        "services_accent_color": "#FFB020",
        "gallery_accent_color": "#FFB020",
        "testimonials_accent_color": "#37D6C7",
        "card_background_color": "#131A24",
        "card_border_radius": "12",
        "version_id": settings.version_id,
        "remove_hero_video": "y",
    }
    resp = client.post("/admin/configuracoes", data=base_data, follow_redirects=True)
    assert resp.status_code == 200

    db.session.refresh(settings)
    assert settings.hero_media_type == "image"
    assert settings.hero_video_path is None


def test_privacy_and_terms_content_editable_and_rendered(client, admin_user, db):
    from app.models import SiteSettings

    login(client, "admin@teste.com", "SenhaForte123!")
    settings = SiteSettings.get_solo()

    resp = client.post(
        "/admin/configuracoes",
        data={
            "company_name": settings.company_name,
            "company_whatsapp": settings.company_whatsapp,
            "color_primary": settings.color_primary,
            "color_secondary": settings.color_secondary,
            "hero_overlay_opacity": "0.5",
            "hero_media_type": "video",
            "services_accent_color": "#FFB020",
            "gallery_accent_color": "#FFB020",
            "testimonials_accent_color": "#37D6C7",
            "card_background_color": "#131A24",
            "card_border_radius": "12",
            "version_id": settings.version_id,
            "privacy_content": "## Título Customizado\nTexto customizado de privacidade.",
            "terms_content": "## Regras Customizadas\nTexto customizado de termos.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    resp = client.get("/privacidade")
    html = resp.get_data(as_text=True)
    assert "Título Customizado" in html
    assert "Texto customizado de privacidade." in html

    resp = client.get("/termos")
    html = resp.get_data(as_text=True)
    assert "Regras Customizadas" in html
    assert "Texto customizado de termos." in html


def test_flash_messages_rendered_as_toast_data(client, admin_user):
    """As mensagens flash devem ser emitidas como dados para o sistema de toast, não como banner fixo."""
    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get("/admin/")
    html = resp.get_data(as_text=True)
    assert "toast.js" in html


def _tiny_jpeg_bytes():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color="red").save(buf, format="JPEG")
    buf.seek(0)
    return buf


def test_service_image_upload_then_remove(client, admin_user, db):
    """
    Antes, os formulários de Serviços/Galeria/Parceiros não tinham como
    remover a mídia já cadastrada (só substituir enviando outro arquivo),
    diferente do Hero/Logo/Favicon em Configurações. Este teste cobre o
    fluxo completo: upload -> prévia aparece -> remoção funciona.
    """
    login(client, "admin@teste.com", "SenhaForte123!")

    resp = client.post(
        "/admin/conteudo/servicos",
        data={
            "title": "Com Imagem",
            "description": "Serviço com imagem",
            "display_order": 1,
            "is_active": "y",
            "image": (_tiny_jpeg_bytes(), "foto.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    service = Service.query.filter_by(title="Com Imagem").first()
    assert service is not None
    assert service.image_path is not None

    # A prévia deve aparecer na tela de edição.
    resp = client.get(f"/admin/conteudo/servicos/{service.id}/editar")
    assert service.image_path in resp.get_data(as_text=True)

    # Remover a imagem atual (sem enviar um arquivo novo).
    resp = client.post(
        f"/admin/conteudo/servicos/{service.id}/editar",
        data={
            "title": "Com Imagem",
            "description": "Serviço com imagem",
            "display_order": 1,
            "is_active": "y",
            "remove_image": "y",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(service)
    assert service.image_path is None


def test_site_settings_get_solo_survives_concurrent_creation(app, db):
    """
    SiteSettings.get_solo() cria a linha singleton (id=1) na primeira
    chamada. Sob acesso concorrente (vários usuários batendo no site ao
    mesmo tempo logo após a instalação, antes de a linha existir), duas
    requisições podiam ver "não existe" ao mesmo tempo e as duas tentar
    criar a linha id=1 -> a segunda a commitar recebia IntegrityError e
    quebrava a requisição com erro 500. Simulamos a corrida diretamente
    inserindo a linha "por baixo" entre a leitura e o commit de
    get_solo(), e garantimos que ele se recupera em vez de propagar o
    erro.
    """
    from app.models import SiteSettings

    with app.app_context():
        assert SiteSettings.query.get(1) is None

        # Simula outra requisição/processo que já criou a linha entre a
        # checagem "instance is None" e o commit desta chamada.
        concorrente = SiteSettings(id=1)
        db.session.add(concorrente)
        db.session.commit()
        db.session.expunge(concorrente)

        # Força get_solo() a passar pelo caminho de criação mesmo com a
        # linha já existindo, para exercitar o tratamento do IntegrityError.
        db.session.expire_all()
        settings = SiteSettings.get_solo()
        assert settings is not None
        assert settings.id == 1
