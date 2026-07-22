"""
Seções personalizadas: o admin pode criar/editar/remover seções extras do
site (além de Vantagens/Galeria/Depoimentos), cada uma com seus próprios
cartões — cobre o CRUD, a geração de slugs únicos/sem colisão com as
âncoras fixas do site, a reordenação escopada por seção, e a exibição
condicional no site público (só aparece se estiver ativa E tiver pelo
menos um cartão ativo).
"""
from app.models import CustomSection, CustomSectionItem
from tests.conftest import login


def _create_section(client, nav_label="Planos", heading="Nossos Planos", is_active=True):
    return client.post(
        "/admin/conteudo/secoes",
        data={"nav_label": nav_label, "heading": heading, "subtitle": "", "is_active": "y" if is_active else ""},
        follow_redirects=True,
    )


def test_create_custom_section_generates_slug(client, admin_user, db):
    login(client, "admin@teste.com", "SenhaForte123!")
    resp = _create_section(client, nav_label="Planos", heading="Nossos Planos")
    assert resp.status_code == 200

    section = CustomSection.query.filter_by(nav_label="Planos").first()
    assert section is not None
    assert section.slug == "planos"
    assert section.is_active is True


def test_custom_section_slug_never_collides_with_reserved_anchors(client, admin_user, db):
    """
    Um admin criando uma seção chamada "Serviços" (ou "Depoimentos") não
    pode gerar um slug igual às âncoras fixas do site (#servicos,
    #depoimentos etc.) — dois elementos com o mesmo id quebrariam a
    navegação por link.
    """
    login(client, "admin@teste.com", "SenhaForte123!")
    resp = _create_section(client, nav_label="Serviços", heading="Nossos Serviços Extras")
    assert resp.status_code == 200

    section = CustomSection.query.filter_by(nav_label="Serviços").first()
    assert section is not None
    assert section.slug not in {"topo", "hero", "servicos", "galeria", "depoimentos", "contato"}


def test_custom_section_slug_stays_unique_across_duplicated_names(client, admin_user, db):
    login(client, "admin@teste.com", "SenhaForte123!")
    _create_section(client, nav_label="Planos", heading="Planos A")
    _create_section(client, nav_label="Planos", heading="Planos B")

    sections = CustomSection.query.filter_by(nav_label="Planos").order_by(CustomSection.id).all()
    assert len(sections) == 2
    assert sections[0].slug != sections[1].slug


def test_edit_custom_section_updates_fields_without_bugs(client, admin_user, db):
    login(client, "admin@teste.com", "SenhaForte123!")
    _create_section(client, nav_label="Planos", heading="Nossos Planos")
    section = CustomSection.query.filter_by(nav_label="Planos").first()

    resp = client.post(
        f"/admin/conteudo/secoes/{section.id}/editar",
        data={"nav_label": "Planos", "heading": "Planos Atualizados", "subtitle": "Escolha o ideal para você", "is_active": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(section)
    assert section.heading == "Planos Atualizados"
    assert section.subtitle == "Escolha o ideal para você"


def test_delete_custom_section_removes_its_items(client, admin_user, db):
    login(client, "admin@teste.com", "SenhaForte123!")
    _create_section(client, nav_label="Planos", heading="Nossos Planos")
    section = CustomSection.query.filter_by(nav_label="Planos").first()
    item = CustomSectionItem(section_id=section.id, title="Plano A", display_order=0, is_active=True)
    db.session.add(item)
    db.session.commit()

    resp = client.post(f"/admin/conteudo/secoes/{section.id}/excluir", follow_redirects=True)
    assert resp.status_code == 200
    assert CustomSection.query.get(section.id) is None
    assert CustomSectionItem.query.filter_by(section_id=section.id).count() == 0


def test_create_and_edit_custom_section_item(client, admin_user, db):
    login(client, "admin@teste.com", "SenhaForte123!")
    _create_section(client, nav_label="Planos", heading="Nossos Planos")
    section = CustomSection.query.filter_by(nav_label="Planos").first()

    resp = client.post(
        f"/admin/conteudo/secoes/{section.id}/itens",
        data={"title": "Plano Básico", "description": "Ideal para começar", "is_active": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    item = CustomSectionItem.query.filter_by(section_id=section.id, title="Plano Básico").first()
    assert item is not None

    resp = client.post(
        f"/admin/conteudo/secoes/{section.id}/itens/{item.id}/editar",
        data={"title": "Plano Básico Renovado", "description": "Ideal para começar", "is_active": "y"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(item)
    assert item.title == "Plano Básico Renovado"


def test_custom_section_item_delete_scoped_to_its_section(client, admin_user, db):
    """Excluir um cartão de uma seção não pode afetar cartões de outra."""
    login(client, "admin@teste.com", "SenhaForte123!")
    _create_section(client, nav_label="Planos", heading="Nossos Planos")
    _create_section(client, nav_label="Equipe", heading="Nossa Equipe")
    section_a = CustomSection.query.filter_by(nav_label="Planos").first()
    section_b = CustomSection.query.filter_by(nav_label="Equipe").first()

    item_a = CustomSectionItem(section_id=section_a.id, title="Item A", display_order=0, is_active=True)
    item_b = CustomSectionItem(section_id=section_b.id, title="Item B", display_order=0, is_active=True)
    db.session.add_all([item_a, item_b])
    db.session.commit()

    # Tentar excluir o item B usando a URL da seção A não pode funcionar
    # (o item não pertence a essa seção) — evita um admin apagar por
    # engano um cartão de outra seção via URL manipulada.
    resp = client.post(f"/admin/conteudo/secoes/{section_a.id}/itens/{item_b.id}/excluir")
    assert resp.status_code == 404
    assert CustomSectionItem.query.get(item_b.id) is not None


def test_custom_section_items_reorder_is_scoped_per_section(client, admin_user, db):
    """
    Reordenar os cartões de UMA seção não pode misturar ou corromper a
    ordem dos cartões de outra seção.
    """
    login(client, "admin@teste.com", "SenhaForte123!")
    _create_section(client, nav_label="Planos", heading="Nossos Planos")
    _create_section(client, nav_label="Equipe", heading="Nossa Equipe")
    section_a = CustomSection.query.filter_by(nav_label="Planos").first()
    section_b = CustomSection.query.filter_by(nav_label="Equipe").first()

    a1 = CustomSectionItem(section_id=section_a.id, title="A1", display_order=0, is_active=True)
    a2 = CustomSectionItem(section_id=section_a.id, title="A2", display_order=1, is_active=True)
    b1 = CustomSectionItem(section_id=section_b.id, title="B1", display_order=0, is_active=True)
    db.session.add_all([a1, a2, b1])
    db.session.commit()

    resp = client.post(
        f"/admin/conteudo/secoes/{section_a.id}/itens/reordenar",
        json={"order": [a2.id, a1.id]},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    db.session.refresh(a1)
    db.session.refresh(a2)
    db.session.refresh(b1)
    assert a2.display_order == 0
    assert a1.display_order == 1
    assert b1.display_order == 0  # intocado


def test_custom_sections_reorder(client, admin_user, db):
    login(client, "admin@teste.com", "SenhaForte123!")
    _create_section(client, nav_label="Planos", heading="Nossos Planos")
    _create_section(client, nav_label="Equipe", heading="Nossa Equipe")
    section_a = CustomSection.query.filter_by(nav_label="Planos").first()
    section_b = CustomSection.query.filter_by(nav_label="Equipe").first()

    resp = client.post("/admin/conteudo/secoes/reordenar", json={"order": [section_b.id, section_a.id]})
    assert resp.status_code == 200
    db.session.refresh(section_a)
    db.session.refresh(section_b)
    assert section_b.display_order == 0
    assert section_a.display_order == 1


def test_public_site_shows_active_custom_section_with_active_item(client, db):
    section = CustomSection(nav_label="Planos", heading="Nossos Planos", slug="planos", display_order=0, is_active=True)
    db.session.add(section)
    db.session.commit()
    item = CustomSectionItem(section_id=section.id, title="Plano Ouro", description="O melhor plano", display_order=0, is_active=True)
    db.session.add(item)
    db.session.commit()

    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert 'id="planos"' in html
    assert "Nossos Planos" in html
    assert "Plano Ouro" in html
    assert 'href="#planos"' in html


def test_public_site_hides_inactive_custom_section(client, db):
    section = CustomSection(nav_label="Planos", heading="Nossos Planos", slug="planos", display_order=0, is_active=False)
    db.session.add(section)
    db.session.commit()
    item = CustomSectionItem(section_id=section.id, title="Plano Ouro", display_order=0, is_active=True)
    db.session.add(item)
    db.session.commit()

    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert 'id="planos"' not in html


def test_public_site_hides_active_section_without_active_items(client, db):
    """Uma seção ativa mas sem nenhum cartão ativo não deve aparecer no menu nem na página (evita um bloco vazio)."""
    section = CustomSection(nav_label="Planos", heading="Nossos Planos", slug="planos", display_order=0, is_active=True)
    db.session.add(section)
    db.session.commit()
    item = CustomSectionItem(section_id=section.id, title="Plano Ouro", display_order=0, is_active=False)
    db.session.add(item)
    db.session.commit()

    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert 'id="planos"' not in html
    assert 'href="#planos"' not in html


def test_public_site_hides_contact_extras_when_empty(client, db):
    """Sem e-mail nem endereço cadastrados, o bloco "Mais contatos" não deve aparecer abaixo do botão do WhatsApp."""
    from app.models import SiteSettings

    settings = SiteSettings.get_solo()
    settings.company_email = None
    settings.company_address = None
    db.session.commit()

    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert "Mais contatos" not in html


def test_public_site_shows_contact_extras_when_present(client, db):
    from app.models import SiteSettings

    settings = SiteSettings.get_solo()
    settings.company_email = "contato@exemplo.com"
    settings.company_address = None
    db.session.commit()

    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert "Mais contatos" in html
    assert "contato@exemplo.com" in html
