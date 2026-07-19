import enum
import secrets
from datetime import datetime, timezone

from app.extensions import db


class ProposalStatus(str, enum.Enum):
    NOVO = "novo"
    EM_ANDAMENTO = "em_andamento"
    CONTATADO = "contatado"
    CONVERTIDO = "convertido"
    ARQUIVADO = "arquivado"


STATUS_LABELS = {
    ProposalStatus.NOVO: "Novo",
    ProposalStatus.EM_ANDAMENTO: "Em andamento",
    ProposalStatus.CONTATADO: "Contatado",
    ProposalStatus.CONVERTIDO: "Convertido",
    ProposalStatus.ARQUIVADO: "Arquivado",
}


def _gen_public_ref() -> str:
    """Gera uma referência pública curta e não sequencial (evita enumeração)."""
    return secrets.token_hex(5).upper()


class Proposal(db.Model):
    """Solicitação de proposta enviada pelo formulário público do site."""

    __tablename__ = "proposals"

    id = db.Column(db.Integer, primary_key=True)
    public_ref = db.Column(
        db.String(16), unique=True, nullable=False, default=_gen_public_ref, index=True
    )

    # Dados do cliente
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(190), nullable=False, index=True)
    phone = db.Column(db.String(30), nullable=False)
    company_name = db.Column(db.String(150), nullable=True)
    message = db.Column(db.Text, nullable=True)
    segment = db.Column(db.String(100), nullable=True)  # ex.: academia, clínica, condomínio
    preferred_locations = db.Column(db.String(255), nullable=True)
    budget_range = db.Column(db.String(60), nullable=True)

    status = db.Column(
        db.Enum(ProposalStatus, name="proposal_status"),
        nullable=False,
        default=ProposalStatus.NOVO,
        index=True,
    )
    internal_notes = db.Column(db.Text, nullable=True)

    # Metadados / auditoria de origem
    source = db.Column(db.String(50), nullable=False, default="site")
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)

    contacted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    contacted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    contacted_by = db.relationship("User", foreign_keys=[contacted_by_id])

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Concorrência: evita que dois administradores sobrescrevam status/anotações
    # um do outro sem perceber (optimistic locking).
    version_id = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version_id}

    __table_args__ = (
        db.Index("ix_proposals_status_created", "status", "created_at"),
    )

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status.value)

    @property
    def phone_digits(self) -> str:
        return "".join(ch for ch in (self.phone or "") if ch.isdigit())

    def to_dict(self):
        return {
            "id": self.id,
            "public_ref": self.public_ref,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "company_name": self.company_name,
            "message": self.message,
            "segment": self.segment,
            "preferred_locations": self.preferred_locations,
            "budget_range": self.budget_range,
            "status": self.status.value,
            "status_label": self.status_label,
            "internal_notes": self.internal_notes,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "contacted_at": self.contacted_at.isoformat() if self.contacted_at else None,
            "contacted_by": self.contacted_by.name if self.contacted_by else None,
        }

    def __repr__(self):
        return f"<Proposal {self.public_ref} {self.name!r} ({self.status.value})>"
