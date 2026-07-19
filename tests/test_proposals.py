from app.models import Proposal
from app.models.proposal import ProposalStatus
from tests.conftest import login


def test_submit_proposal_creates_record(client, db):
    resp = client.post(
        "/solicitar-proposta",
        data={
            "name": "João da Silva",
            "email": "joao@example.com",
            "phone": "67999998888",
            "company_name": "Academia Vitalis",
            "message": "Quero anunciar",
            "confirm_hp": "",  # honeypot vazio
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    proposal = Proposal.query.filter_by(email="joao@example.com").first()
    assert proposal is not None
    assert proposal.status == ProposalStatus.NOVO
    assert proposal.public_ref is not None


def test_submit_proposal_honeypot_blocks_bots(client, db):
    client.post(
        "/solicitar-proposta",
        data={
            "name": "Bot Malicioso",
            "email": "bot@example.com",
            "phone": "67999998888",
            "confirm_hp": "http://spam.com",  # honeypot preenchido = bot
        },
        follow_redirects=True,
    )
    assert Proposal.query.filter_by(email="bot@example.com").first() is None


def test_submit_proposal_validates_required_fields(client, db):
    resp = client.post("/solicitar-proposta", data={"name": ""}, follow_redirects=True)
    assert resp.status_code == 200
    assert Proposal.query.count() == 0


def test_admin_can_view_proposal_list(client, admin_user, db):
    proposal = Proposal(name="Maria", email="maria@example.com", phone="67988887777")
    db.session.add(proposal)
    db.session.commit()

    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get("/admin/solicitacoes")
    assert resp.status_code == 200
    assert "Maria" in resp.get_data(as_text=True)


def test_admin_can_view_proposal_detail(client, admin_user, db):
    proposal = Proposal(name="Carlos", email="carlos@example.com", phone="67977776666")
    db.session.add(proposal)
    db.session.commit()

    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get(f"/admin/solicitacoes/{proposal.id}")
    assert resp.status_code == 200
    assert "Carlos" in resp.get_data(as_text=True)


def test_whatsapp_redirect_generates_valid_link(client, admin_user, db):
    proposal = Proposal(name="Ana", email="ana@example.com", phone="67966665555")
    db.session.add(proposal)
    db.session.commit()

    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get(f"/admin/solicitacoes/{proposal.id}/whatsapp", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["Location"]
    assert location.startswith("https://wa.me/5567966665555")
    assert "Ana" in location or "%20Ana" in location or "Ana%21" in location


def test_status_update_with_stale_version_is_rejected(client, admin_user, db):
    proposal = Proposal(name="Pedro", email="pedro@example.com", phone="67955554444")
    db.session.add(proposal)
    db.session.commit()

    login(client, "admin@teste.com", "SenhaForte123!")
    stale_version = proposal.version_id

    # Simula alteração concorrente por outro processo/admin
    proposal.internal_notes = "alterado por outro admin"
    proposal.version_id += 1
    db.session.commit()

    resp = client.post(
        f"/admin/solicitacoes/{proposal.id}/status",
        data={"status": "contatado", "internal_notes": "minha nota", "version_id": stale_version},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(proposal)
    assert proposal.status != ProposalStatus.CONTATADO


def test_viewer_role_cannot_change_status(client, db):
    from app.models import User, UserRole

    viewer = User(name="Visualizador", email="viewer@teste.com", role=UserRole.VIEWER)
    viewer.set_password("SenhaForte123!")
    db.session.add(viewer)
    proposal = Proposal(name="Lucas", email="lucas@example.com", phone="67944443333")
    db.session.add(proposal)
    db.session.commit()

    login(client, "viewer@teste.com", "SenhaForte123!")
    resp = client.post(
        f"/admin/solicitacoes/{proposal.id}/status",
        data={"status": "contatado", "internal_notes": "", "version_id": proposal.version_id},
    )
    assert resp.status_code == 403
