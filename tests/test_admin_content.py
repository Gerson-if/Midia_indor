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
            "version_id": settings.version_id,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(settings)
    assert settings.company_name == "Nova Empresa"
