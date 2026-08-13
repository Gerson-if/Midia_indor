from datetime import datetime, timezone

from app.extensions import db
from app.models.tenant import TenantScopedMixin


class PageView(TenantScopedMixin, db.Model):
    """
    Uma visualização de página do site público (dashboard do admin: visitas,
    tempo de permanência e origem do tráfego).

    session_id identifica o navegador (cookie "nx_vid", sem login nenhum
    envolvido) -- usado só para contar visitantes únicos, nunca para
    identificar uma pessoa. duration_seconds chega depois, via um "beacon"
    disparado pelo navegador quando o visitante sai da página (pode nunca
    chegar, ex.: aba fechada à força ou o próprio navegador bloqueando).
    """

    __tablename__ = "page_views"

    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(255), nullable=False)
    session_id = db.Column(db.String(36), nullable=False, index=True)

    referrer_source = db.Column(db.String(80), nullable=True)  # ex.: "Instagram", "Google", "Direto"
    referrer_host = db.Column(db.String(255), nullable=True)

    duration_seconds = db.Column(db.Integer, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )

    def __repr__(self):
        return f"<PageView {self.path} ({self.referrer_source}) at {self.created_at}>"
