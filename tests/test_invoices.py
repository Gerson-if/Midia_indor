from datetime import date, timedelta

from app.models import Invoice, InvoiceStatus
from tests.conftest import login
from tests.test_superadmin import login_superadmin


def test_superadmin_creates_invoice_with_items_and_recurring_flag(client, super_admin_user, tenant, db):
    login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")

    resp = client.post(
        f"/super/paginas/{tenant.id}/faturas/nova",
        data={
            "title": "Mensalidade Agosto/2026",
            "due_date": "2026-08-25",
            "is_recurring": "y",
            "service_cutoff_at": "2026-09-05",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    invoice = Invoice.query.filter_by(tenant_id=tenant.id).first()
    assert invoice is not None
    assert invoice.is_recurring is True
    assert invoice.service_cutoff_at == date(2026, 9, 5)
    assert invoice.status == InvoiceStatus.PENDING

    resp = client.post(
        f"/super/faturas/{invoice.id}/itens",
        data={"description": "Mensalidade do plano Padrão", "amount": "199.90"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(invoice)
    assert len(invoice.items) == 1
    assert float(invoice.total) == 199.90


def test_superadmin_marks_invoice_paid_and_cancel(client, super_admin_user, tenant, db):
    login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")
    invoice = Invoice(tenant_id=tenant.id, title="Fatura X", due_date=date.today())
    db.session.add(invoice)
    db.session.commit()

    resp = client.post(f"/super/faturas/{invoice.id}/marcar-paga", follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(invoice)
    assert invoice.status == InvoiceStatus.PAID
    assert invoice.paid_at is not None

    invoice2 = Invoice(tenant_id=tenant.id, title="Fatura Y", due_date=date.today())
    db.session.add(invoice2)
    db.session.commit()
    resp = client.post(f"/super/faturas/{invoice2.id}/cancelar", follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(invoice2)
    assert invoice2.status == InvoiceStatus.CANCELED


def test_superadmin_edits_pending_invoice_including_cutoff_date(client, super_admin_user, tenant, db):
    login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")
    invoice = Invoice(tenant_id=tenant.id, title="Mensalidade Julho", due_date=date(2026, 7, 25))
    db.session.add(invoice)
    db.session.commit()

    resp = client.post(
        f"/super/faturas/{invoice.id}/editar",
        data={
            "title": "Mensalidade Agosto",
            "due_date": "2026-08-25",
            "is_recurring": "y",
            "service_cutoff_at": "2026-09-10",
            "notes": "Reajuste combinado com o cliente.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(invoice)
    assert invoice.title == "Mensalidade Agosto"
    assert invoice.due_date == date(2026, 8, 25)
    assert invoice.is_recurring is True
    assert invoice.service_cutoff_at == date(2026, 9, 10)
    assert invoice.notes == "Reajuste combinado com o cliente."


def test_superadmin_cannot_edit_or_delete_paid_invoice(client, super_admin_user, tenant, db):
    login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")
    invoice = Invoice(tenant_id=tenant.id, title="Fatura Paga", due_date=date.today(), status=InvoiceStatus.PAID)
    db.session.add(invoice)
    db.session.commit()
    invoice_id = invoice.id

    resp = client.post(
        f"/super/faturas/{invoice_id}/editar",
        data={"title": "Tentando mudar", "due_date": "2026-08-25", "service_cutoff_at": ""},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(invoice)
    assert invoice.title == "Fatura Paga"

    resp = client.post(f"/super/faturas/{invoice_id}/excluir", follow_redirects=True)
    assert resp.status_code == 200
    assert Invoice.query.filter_by(id=invoice_id).first() is not None


def test_superadmin_deletes_pending_invoice(client, super_admin_user, tenant, db):
    login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")
    invoice = Invoice(tenant_id=tenant.id, title="Fatura Lançada por Engano", due_date=date.today())
    db.session.add(invoice)
    db.session.commit()
    invoice_id = invoice.id

    resp = client.post(f"/super/faturas/{invoice_id}/excluir", follow_redirects=True)
    assert resp.status_code == 200
    assert Invoice.query.filter_by(id=invoice_id).first() is None


def test_invoices_overview_filters_by_status(client, super_admin_user, tenant, db):
    login_superadmin(client, "superadmin@teste.com", "SenhaForte123!")
    db.session.add(Invoice(tenant_id=tenant.id, title="Fatura Aberta", due_date=date.today()))
    db.session.add(
        Invoice(tenant_id=tenant.id, title="Fatura Quitada", due_date=date.today(), status=InvoiceStatus.PAID)
    )
    db.session.commit()

    resp = client.get("/super/faturas?status=pending")
    html = resp.get_data(as_text=True)
    assert "Fatura Aberta" in html
    assert "Fatura Quitada" not in html

    resp = client.get("/super/faturas?status=paid")
    html = resp.get_data(as_text=True)
    assert "Fatura Quitada" in html
    assert "Fatura Aberta" not in html


def test_regular_admin_cannot_manage_invoices(client, admin_user, tenant, db):
    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get("/super/faturas")
    assert resp.status_code in (302, 403)


def test_admin_sees_own_invoices_in_subscription_page(client, admin_user, tenant, db):
    invoice = Invoice(
        tenant_id=tenant.id,
        title="Mensalidade",
        due_date=date.today() + timedelta(days=10),
        service_cutoff_at=date.today() + timedelta(days=20),
    )
    db.session.add(invoice)
    db.session.flush()
    from app.models import InvoiceItem

    db.session.add(InvoiceItem(tenant_id=tenant.id, invoice_id=invoice.id, description="Plano Padrão", amount=199.90))
    db.session.commit()

    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get("/admin/assinatura", headers={"Host": "localhost"})
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Mensalidade" in html
    assert "199.90" in html
    assert "risco de desligamento" in html


def test_admin_only_sees_invoices_from_own_tenant(client, admin_user, tenant, other_tenant, db):
    db.session.add(Invoice(tenant_id=tenant.id, title="Fatura da Minha Página", due_date=date.today()))
    db.session.add(Invoice(tenant_id=other_tenant.id, title="Fatura de Outra Página", due_date=date.today()))
    db.session.commit()

    login(client, "admin@teste.com", "SenhaForte123!")
    resp = client.get("/admin/assinatura", headers={"Host": "localhost"})
    html = resp.get_data(as_text=True)
    assert "Fatura da Minha Página" in html
    assert "Fatura de Outra Página" not in html


def test_editor_cannot_access_subscription_page(client, editor_user, tenant, db):
    login(client, "editor@teste.com", "SenhaForte123!")
    resp = client.get("/admin/assinatura", headers={"Host": "localhost"})
    assert resp.status_code == 403
