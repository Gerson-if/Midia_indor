"""
Geração do link "wa.me" com mensagem pré-formatada para contato com o
cliente que enviou uma solicitação de proposta.

A mensagem é escrita da perspectiva da empresa, já contextualizando o
cliente sobre os dados que ele enviou — assim o atendente não precisa
digitar nada manualmente e o cliente reconhece imediatamente do que se trata.
"""
from urllib.parse import quote

from app.models.proposal import Proposal


def _normalize_phone(raw_phone: str) -> str:
    """
    Normaliza um telefone brasileiro para o formato exigido pelo wa.me:
    apenas dígitos, com código do país (55) na frente.
    """
    digits = "".join(ch for ch in (raw_phone or "") if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("55") and len(digits) >= 12:
        return digits
    return f"55{digits}"


def build_client_whatsapp_message(proposal: Proposal, company_name: str) -> str:
    """Monta o texto formatado que será pré-preenchido na conversa com o cliente."""
    lines = [
        f"Olá, {proposal.name}! 👋",
        f"Aqui é da equipe *{company_name}*.",
        "",
        "Recebemos sua solicitação de proposta com os seguintes dados:",
        f"🆔 Referência: {proposal.public_ref}",
        f"📅 Data: {proposal.created_at.strftime('%d/%m/%Y às %H:%M')}",
    ]

    if proposal.company_name:
        lines.append(f"🏢 Empresa: {proposal.company_name}")
    if proposal.segment:
        lines.append(f"🏷️ Segmento: {proposal.segment}")
    if proposal.preferred_locations:
        lines.append(f"📍 Locais de interesse: {proposal.preferred_locations}")
    if proposal.budget_range:
        lines.append(f"💰 Faixa de investimento: {proposal.budget_range}")
    if proposal.message:
        lines.append("")
        lines.append("📝 Mensagem enviada:")
        lines.append(f"“{proposal.message.strip()}”")

    lines += [
        "",
        "Podemos conversar agora para entender melhor sua necessidade e",
        "apresentar as melhores opções de mídia indoor para sua marca?",
    ]

    return "\n".join(lines)


def build_client_whatsapp_link(proposal: Proposal, company_name: str) -> str:
    """Retorna a URL completa https://wa.me/<telefone>?text=<mensagem codificada>."""
    phone = _normalize_phone(proposal.phone)
    message = build_client_whatsapp_message(proposal, company_name)
    encoded_message = quote(message)
    if not phone:
        return f"https://wa.me/?text={encoded_message}"
    return f"https://wa.me/{phone}?text={encoded_message}"
