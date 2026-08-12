from app.models import GalleryItem
from tests.conftest import login


def test_admin_creates_gallery_item_with_detail_page(client, admin_user, db, tenant):
    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.post(
        "/admin/conteudo/galeria",
        data={
            "title": "Pizzaria Italia",
            "category": "Restaurantes",
            "is_active": "y",
            "has_detail_page": "y",
            "detail_description": "Ponto de alta retenção no centro da cidade.",
            "detail_tags": "Delivery e Alimentação, Barbearias e Salões, Eventos e Shows",
            "detail_monthly_reach": "+4.500",
            "detail_retention_time": "45 min",
            "detail_visibility_percent": "95",
            "detail_cta_message": "Olá! Quero anunciar na Pizzaria Italia.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    item = GalleryItem.query.filter_by(tenant_id=tenant.id, title="Pizzaria Italia").first()
    assert item is not None
    assert item.has_detail_page is True
    assert item.detail_description == "Ponto de alta retenção no centro da cidade."
    assert item.detail_tags_list == ["Delivery e Alimentação", "Barbearias e Salões", "Eventos e Shows"]
    assert item.detail_monthly_reach == "+4.500"
    assert item.detail_visibility_percent == 95


def test_admin_can_toggle_detail_page_off(client, admin_user, db, tenant):
    item = GalleryItem(
        tenant_id=tenant.id, title="Ponto A", category="Cat", has_detail_page=True, detail_description="Texto"
    )
    db.session.add(item)
    db.session.commit()

    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.post(
        f"/admin/conteudo/galeria/{item.id}/editar",
        data={"title": "Ponto A", "category": "Cat", "is_active": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(item)
    assert item.has_detail_page is False


def test_public_gallery_detail_page_renders_when_enabled(client, db, tenant):
    item = GalleryItem(
        tenant_id=tenant.id,
        title="Pizzaria Italia",
        category="Restaurantes",
        is_active=True,
        has_detail_page=True,
        detail_description="Ponto de alta retenção no centro da cidade.",
        detail_tags="Delivery e Alimentação, Barbearias e Salões",
        detail_monthly_reach="+4.500",
        detail_retention_time="45 min",
        detail_visibility_percent=95,
    )
    db.session.add(item)
    db.session.commit()

    resp = client.get(f"/ponto/{item.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Pizzaria Italia" in html
    assert "Ponto de alta retenção" in html
    assert "Delivery e Alimentação" in html
    assert "+4.500" in html
    assert "45 min" in html
    assert "95%" in html
    assert "wa.me/" in html


def test_public_gallery_detail_page_404s_when_disabled(client, db, tenant):
    item = GalleryItem(tenant_id=tenant.id, title="Ponto B", category="Cat", is_active=True, has_detail_page=False)
    db.session.add(item)
    db.session.commit()

    resp = client.get(f"/ponto/{item.id}")
    assert resp.status_code == 404


def test_public_gallery_detail_page_404s_when_item_inactive(client, db, tenant):
    item = GalleryItem(tenant_id=tenant.id, title="Ponto C", category="Cat", is_active=False, has_detail_page=True)
    db.session.add(item)
    db.session.commit()

    resp = client.get(f"/ponto/{item.id}")
    assert resp.status_code == 404


def test_index_links_only_gallery_items_with_detail_page(client, db, tenant):
    with_detail = GalleryItem(
        tenant_id=tenant.id, title="Com Detalhe", category="Cat", is_active=True, has_detail_page=True
    )
    without_detail = GalleryItem(
        tenant_id=tenant.id, title="Sem Detalhe", category="Cat", is_active=True, has_detail_page=False
    )
    db.session.add_all([with_detail, without_detail])
    db.session.commit()

    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert f'href="/ponto/{with_detail.id}"' in html
    assert f'/ponto/{without_detail.id}"' not in html
