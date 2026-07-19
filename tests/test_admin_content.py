from app.models import Service
from tests.conftest import login


def test_admin_dashboard_loads(client, admin_user):
    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert "Visão Geral" in resp.get_data(as_text=True)


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
