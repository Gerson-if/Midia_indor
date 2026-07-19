from datetime import datetime, timezone

from app.extensions import db


class AuditLog(db.Model):
    """
    Registro de auditoria de ações sensíveis (login, alteração de status,
    exclusão de registros, alterações de configuração, etc.).

    Mantido como tabela append-only: nunca é editado ou apagado pela aplicação.
    """

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    user_email_snapshot = db.Column(db.String(190), nullable=True)

    action = db.Column(db.String(80), nullable=False, index=True)  # ex.: "proposal.status_changed"
    entity_type = db.Column(db.String(80), nullable=True)          # ex.: "Proposal"
    entity_id = db.Column(db.String(40), nullable=True)

    description = db.Column(db.String(500), nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)  # payload extra serializado em JSON

    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    user = db.relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<AuditLog {self.action} by {self.user_email_snapshot} at {self.created_at}>"
