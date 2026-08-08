import enum
import re
from datetime import datetime, timezone

from sqlalchemy.orm import declared_attr

from app.extensions import db


class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"  # bloqueado pelo super admin (ex.: pendência financeira)


def normalize_domain(raw: str) -> str:
    """Normaliza um domínio informado pelo super admin: remove protocolo,
    caminho, porta e espaços, e força minúsculas (ex.:
    "HTTPS://Cliente.com/ " -> "cliente.com")."""
    value = (raw or "").strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/")[0]
    value = value.split(":")[0]
    return value


class Tenant(db.Model):
    """
    Uma "página" (site) de cliente, criada e gerenciada pelo super admin.
    Cada tenant tem um usuário administrador dono (owner_user, relação
    1 usuário = 1 página) e um ou mais domínios/subdomínios (TenantDomain)
    que, ao apontarem para a VPS, fazem o sistema renderizar este site
    automaticamente -- sem qualquer configuração manual além do DNS.
    """

    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    # Identificador interno (só aparece no painel do super admin).
    slug = db.Column(db.String(140), unique=True, nullable=False, index=True)

    status = db.Column(
        db.Enum(TenantStatus, name="tenant_status"), nullable=False, default=TenantStatus.ACTIVE
    )
    # Motivo do bloqueio: informação interna, visível apenas para o admin
    # do próprio tenant e para o super admin -- o visitante final do site
    # público nunca vê isso (ver enforcement em app/utils/tenancy.py).
    blocked_reason = db.Column(db.String(300), nullable=True)
    blocked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    blocked_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", use_alter=True, name="fk_tenants_blocked_by"), nullable=True
    )

    owner_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", use_alter=True, name="fk_tenants_owner_user"),
        unique=True,
        nullable=True,
    )
    owner_user = db.relationship("User", foreign_keys=[owner_user_id], post_update=True)
    blocked_by = db.relationship("User", foreign_keys=[blocked_by_id], post_update=True)

    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    version_id = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version_id}

    domains = db.relationship(
        "TenantDomain",
        backref="tenant",
        cascade="all, delete-orphan",
        order_by="TenantDomain.id",
    )

    @property
    def is_blocked(self) -> bool:
        return self.status == TenantStatus.BLOCKED

    @property
    def primary_domain(self):
        for d in self.domains:
            if d.is_primary:
                return d
        return self.domains[0] if self.domains else None

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "status": self.status.value,
            "is_blocked": self.is_blocked,
            "blocked_reason": self.blocked_reason,
            "domains": [d.domain for d in self.domains],
            "owner_email": self.owner_user.email if self.owner_user else None,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<Tenant {self.slug} ({self.status.value})>"


class TenantDomain(db.Model):
    """Domínio ou subdomínio que, ao ser apontado (DNS) para a VPS, faz o
    sistema renderizar automaticamente o site deste tenant."""

    __tablename__ = "tenant_domains"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    domain = db.Column(db.String(255), unique=True, nullable=False, index=True)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<TenantDomain {self.domain} -> tenant_id={self.tenant_id}>"


class TenantScopedMixin:
    """
    Mixin para models que pertencem a exatamente um tenant (conteúdo do
    site, propostas, configurações). Combinado com o filtro global
    registrado em app/utils/tenancy.py, toda consulta feita durante uma
    requisição enxerga automaticamente só as linhas do tenant resolvido
    pelo domínio de acesso (g.tenant_id) -- sem precisar repetir
    ".filter_by(tenant_id=...)" em cada rota já existente.
    """

    @declared_attr
    def tenant_id(cls):
        return db.Column(
            db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
        )
