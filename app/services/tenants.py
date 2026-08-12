"""
Exclusão definitiva de uma página (tenant) do super admin -- ação
irreversível que remove todo o conteúdo que pertence só a ela.

Feito em ordem explícita (em vez de confiar só no ON DELETE CASCADE
declarado nas migrações) porque:
  - SQLite (usado em dev/testes) não aplica cascade de FK a menos que
    "PRAGMA foreign_keys=ON" seja habilitado por conexão, o que este
    app não faz -- confiar só na cascade do banco deixaria linhas
    órfãs em dev/testes sem avisar nada.
  - audit_logs é intencionalmente append-only (nunca apagado pela
    aplicação -- ver app/models/audit.py): em vez de apagar o
    histórico junto com a página, só desvinculamos (tenant_id e
    user_id viram NULL), preservando o registro -- inclusive o e-mail
    de quem agiu, já congelado em user_email_snapshot.
"""
from app.extensions import db
from app.models import (
    AuditLog,
    CustomSection,
    CustomSectionItem,
    GalleryItem,
    GalleryRecommendation,
    Partner,
    Proposal,
    Service,
    SiteSettings,
    Testimonial,
    User,
)


def delete_tenant(tenant) -> None:
    tenant_id = tenant.id

    # Quebra as referências de volta para users ANTES de apagar os
    # usuários da página -- senão a própria linha do tenant (ainda não
    # apagada neste ponto) bloquearia a exclusão desses usuários via FK
    # (owner_user_id / blocked_by_id).
    tenant.owner_user_id = None
    tenant.blocked_by_id = None
    db.session.flush()

    # Preserva o histórico de auditoria, só desvinculando da página que
    # está sendo apagada.
    AuditLog.query.filter_by(tenant_id=tenant_id).update({"tenant_id": None}, synchronize_session=False)

    user_ids = [row[0] for row in User.query.filter_by(tenant_id=tenant_id).with_entities(User.id).all()]
    if user_ids:
        AuditLog.query.filter(AuditLog.user_id.in_(user_ids)).update(
            {"user_id": None}, synchronize_session=False
        )

    # Filhos antes dos pais (custom_section_items referencia custom_sections;
    # gallery_recommendations referencia gallery_items).
    CustomSectionItem.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
    CustomSection.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
    GalleryRecommendation.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
    GalleryItem.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
    Partner.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
    Proposal.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
    Service.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
    Testimonial.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
    SiteSettings.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
    User.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)

    # tenant_domains tem cascade "all, delete-orphan" na relação ORM
    # (Tenant.domains) -- session.delete() já cuida deles.
    db.session.delete(tenant)
    db.session.commit()
