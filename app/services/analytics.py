"""
Rastreamento de visitas do site público (dashboard do admin: visualizações,
tempo de permanência e origem do tráfego).

Propositalmente simples e só de primeira parte: nenhum script externo,
nenhuma coleta de dado pessoal (nome, e-mail, IP não é salvo), um cookie
próprio só com um identificador aleatório para diferenciar visitantes.
"""
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import g, request

from app.extensions import db
from app.models import PageView

# Endpoints do blueprint "main" que representam uma página de verdade sendo
# vista por um visitante -- de propósito não inclui rotas de API/health
# check/formulário (essas não são "visualizações de página").
TRACKED_ENDPOINTS = {"main.index", "main.gallery_detail", "main.privacidade", "main.termos"}

VISITOR_COOKIE_NAME = "nx_vid"
VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 180  # 180 dias

# Domínios conhecidos -> rótulo de origem exibido no dashboard. Checado por
# "contém", não igualdade exata, pra cobrir subdomínios (ex.: "l.instagram.com").
_KNOWN_SOURCES = (
    ("google.", "Google"),
    ("bing.", "Bing"),
    ("duckduckgo.", "DuckDuckGo"),
    ("yahoo.", "Yahoo"),
    ("instagram.", "Instagram"),
    ("facebook.", "Facebook"),
    ("fb.com", "Facebook"),
    ("wa.me", "WhatsApp"),
    ("whatsapp.", "WhatsApp"),
    ("t.co", "Twitter/X"),
    ("twitter.", "Twitter/X"),
    ("x.com", "Twitter/X"),
    ("linkedin.", "LinkedIn"),
    ("tiktok.", "TikTok"),
    ("youtube.", "YouTube"),
)


def classify_referrer(referrer: str | None, request_host: str) -> tuple[str, str | None]:
    """
    Classifica o Referer (cabeçalho HTTP) num rótulo de origem legível.

    Retorna (rótulo, host_bruto). host_bruto vem sem porta/www, só pra
    depuração -- o rótulo é o que aparece no dashboard.
    """
    if not referrer:
        return "Direto", None

    try:
        host = (urlparse(referrer).hostname or "").lower()
    except ValueError:
        return "Direto", None

    if not host:
        return "Direto", None

    own_host = (request_host or "").split(":")[0].lower()
    if host == own_host or host.endswith(f".{own_host}"):
        return "Navegação interna", host

    for needle, label in _KNOWN_SOURCES:
        if needle in host:
            return label, host

    display_host = re.sub(r"^www\.", "", host)
    return f"Outro ({display_host})", host


def record_page_view() -> None:
    """
    Registra uma visualização de página, se a rota atual for rastreável.

    Chamado num before_request do blueprint "main" -- roda ANTES da rota,
    então não sabe ainda se a resposta será 404 (ex.: /ponto/<id inválido>).
    Aceitável: é uma estatística de uso, não um registro de auditoria, e a
    maioria das ferramentas de analytics tem essa mesma limitação.

    Qualquer erro aqui é engolido (só logado) -- rastrear uma visita nunca
    pode derrubar a página que o visitante veio ver.
    """
    if request.method != "GET" or request.endpoint not in TRACKED_ENDPOINTS:
        return
    if getattr(g, "tenant_id", None) is None:
        return

    try:
        visitor_id = request.cookies.get(VISITOR_COOKIE_NAME)
        g.nx_new_visitor_cookie = not visitor_id
        if not visitor_id:
            visitor_id = str(uuid.uuid4())

        source, host = classify_referrer(request.referrer, request.host)
        view = PageView(
            tenant_id=g.tenant_id,
            path=request.path[:255],
            session_id=visitor_id,
            referrer_source=source,
            referrer_host=host[:255] if host else None,
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(view)
        db.session.commit()

        g.nx_visitor_id = visitor_id
        g.page_view_id = view.id
    except Exception:
        db.session.rollback()
        import logging

        logging.getLogger(__name__).exception("Falha ao registrar page view")


def apply_visitor_cookie(response):
    """
    after_request: grava/renova o cookie do visitante quando record_page_view()
    criou um novo. Só existe como função separada porque before_request não
    tem acesso ao objeto de resposta para poder chamar set_cookie().
    """
    if getattr(g, "nx_new_visitor_cookie", False) and getattr(g, "nx_visitor_id", None):
        response.set_cookie(
            VISITOR_COOKIE_NAME,
            g.nx_visitor_id,
            max_age=VISITOR_COOKIE_MAX_AGE,
            samesite="Lax",
            httponly=True,
        )
    return response
