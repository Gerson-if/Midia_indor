import enum
from datetime import date, datetime, timezone

from app.extensions import db
from app.models.tenant import TenantScopedMixin


class InvoiceStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    CANCELED = "CANCELED"


class Invoice(TenantScopedMixin, db.Model):
    """
    Fatura lançada pelo super admin para uma página (lojista). Tem uma ou
    mais linhas (InvoiceItem) discriminando o que está incluso -- o total
    é sempre a soma delas, nunca um valor digitado à parte, pra nunca
    ficar dessincronizado.
    """

    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.Date, nullable=False)
    status = db.Column(
        db.Enum(InvoiceStatus, name="invoice_status"), nullable=False, default=InvoiceStatus.PENDING
    )
    is_recurring = db.Column(db.Boolean, nullable=False, default=False)

    # Data em que o acesso é encerrado por completo -- diferente de
    # "bloquear" (Tenant.status), que só tira o site público do ar mas
    # mantém o painel acessível. Isto aqui é o aviso de que, se a fatura
    # não for paga até essa data, o fornecedor externo de hospedagem
    # encerra o acesso de vez. Fica só como informação/aviso: quem de
    # fato desliga o serviço é uma ação manual do super admin (bloquear/
    # excluir a página) ou o próprio fornecedor -- o sistema não desliga
    # nada sozinho na data.
    service_cutoff_at = db.Column(db.Date, nullable=True)

    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    items = db.relationship(
        "InvoiceItem",
        backref="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItem.display_order",
    )
    tenant = db.relationship("Tenant", backref=db.backref("invoices", cascade="all, delete-orphan"))

    @property
    def total(self):
        return sum((item.amount for item in self.items), start=0)

    @property
    def is_overdue(self) -> bool:
        return self.status == InvoiceStatus.PENDING and self.due_date < date.today()

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "is_recurring": self.is_recurring,
            "due_date": self.due_date.isoformat(),
            "service_cutoff_at": self.service_cutoff_at.isoformat() if self.service_cutoff_at else None,
            "total": float(self.total),
            "items": [i.to_dict() for i in self.items],
        }

    def __repr__(self):
        return f"<Invoice {self.title} tenant_id={self.tenant_id} status={self.status.value}>"


class InvoiceItem(TenantScopedMixin, db.Model):
    """Uma linha da fatura (discriminação do que está incluso)."""

    __tablename__ = "invoice_items"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(
        db.Integer, db.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {"id": self.id, "description": self.description, "amount": float(self.amount)}

    def __repr__(self):
        return f"<InvoiceItem {self.description} R${self.amount}>"
