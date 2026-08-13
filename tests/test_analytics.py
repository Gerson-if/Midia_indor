from app.models import PageView
from app.services.analytics import classify_referrer
from tests.conftest import login


def test_visiting_public_page_records_a_page_view_and_sets_cookie(client, db, tenant):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "nx_vid" in resp.headers.get("Set-Cookie", "")

    view = PageView.query.filter_by(tenant_id=tenant.id).first()
    assert view is not None
    assert view.path == "/"
    assert view.referrer_source == "Direto"


def test_non_trackable_routes_do_not_record_page_views(client, db, tenant):
    client.get("/healthz")
    assert PageView.query.count() == 0


def test_referrer_classification():
    assert classify_referrer(None, "meusite.com.br") == ("Direto", None)
    assert classify_referrer("https://www.instagram.com/p/xyz", "meusite.com.br") == ("Instagram", "www.instagram.com")
    assert classify_referrer("https://www.google.com/search?q=x", "meusite.com.br") == ("Google", "www.google.com")
    assert classify_referrer("https://meusite.com.br/galeria", "meusite.com.br") == ("Navegação interna", "meusite.com.br")
    label, host = classify_referrer("https://blogdesconhecido.com.br/post", "meusite.com.br")
    assert label == "Outro (blogdesconhecido.com.br)"
    assert host == "blogdesconhecido.com.br"


def test_referrer_classified_from_request_header(client, db, tenant):
    client.get("/", headers={"Referer": "https://www.instagram.com/p/xyz"})
    view = PageView.query.filter_by(tenant_id=tenant.id).first()
    assert view.referrer_source == "Instagram"


def test_track_duration_updates_matching_page_view(client, db, tenant):
    client.get("/")
    view = PageView.query.filter_by(tenant_id=tenant.id).first()
    assert view.duration_seconds is None

    resp = client.post(
        "/api/v1/track/duracao",
        json={"page_view_id": view.id, "duration": 42},
    )
    assert resp.status_code == 204

    db.session.refresh(view)
    assert view.duration_seconds == 42


def test_track_duration_ignores_page_view_from_another_tenant(client, db, tenant, other_tenant):
    other_view = PageView(tenant_id=other_tenant.id, path="/", session_id="22222222-2222-2222-2222-222222222222")
    db.session.add(other_view)
    db.session.commit()

    # Requisição chega pelo domínio "localhost", que resolve para `tenant`
    # -- não pode alterar uma page view que pertence a `other_tenant`.
    resp = client.post(
        "/api/v1/track/duracao",
        json={"page_view_id": other_view.id, "duration": 99},
    )
    assert resp.status_code == 204
    db.session.refresh(other_view)
    assert other_view.duration_seconds is None


def test_track_duration_ignores_invalid_payload(client, db, tenant):
    resp = client.post("/api/v1/track/duracao", json={"page_view_id": "not-an-int", "duration": 42})
    assert resp.status_code == 204

    resp = client.post("/api/v1/track/duracao", json={"page_view_id": 1, "duration": 99999999})
    assert resp.status_code == 204


def test_dashboard_shows_site_traffic_metrics(client, admin_user, db, tenant):
    db.session.add_all(
        [
            PageView(
                tenant_id=tenant.id, path="/", session_id="a", referrer_source="Instagram", duration_seconds=30
            ),
            PageView(
                tenant_id=tenant.id, path="/", session_id="b", referrer_source="Google", duration_seconds=90
            ),
        ]
    )
    db.session.commit()

    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get("/admin/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Tráfego do site" in html
    assert "Instagram" in html
    assert "Google" in html
