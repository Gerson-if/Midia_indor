"""
Renderização do conteúdo das páginas legais (Privacidade / Termos).

O conteúdo é editado em um textarea simples no painel administrativo,
usando uma marcação mínima:
  - Linhas iniciadas com "## " viram títulos de seção.
  - Blocos em que toda linha começa com "- " viram listas.
  - Demais blocos viram parágrafos, com quebras de linha simples
    preservadas dentro do parágrafo.
  - Parágrafos são separados por uma linha em branco.

Importante: navegadores normalizam o valor de um <textarea> para CRLF
("\\r\\n") ao submeter o formulário. Sem normalizar de volta para "\\n"
antes de separar os blocos por linha em branco, TODA a formatação
(títulos, listas, parágrafos e espaçamentos) se perde após uma edição
feita pelo navegador — o texto inteiro vira um único bloco de texto cru.
"""
from markupsafe import Markup, escape


def normalize_newlines(text: str) -> str:
    """Normaliza quebras de linha vindas de navegadores/SOs para '\\n'."""
    if not text:
        return text
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _render_body_lines(body_lines):
    """Renderiza as linhas de um bloco (sem a linha de título, se houver)
    como lista (se todas começarem com "- ") ou como parágrafo único,
    preservando quebras de linha internas via CSS (whitespace-pre-line)."""
    if not body_lines:
        return ""
    if all(line.startswith("- ") for line in body_lines):
        items = "".join(f"<li>{escape(line[2:].strip())}</li>" for line in body_lines)
        return f'<ul class="list-disc list-inside space-y-1">{items}</ul>'
    paragraph = escape("\n".join(body_lines))
    return f'<p class="whitespace-pre-line">{paragraph}</p>'


def render_legal_content(text: str) -> Markup:
    """Converte o texto armazenado em HTML seguro, preservando a formatação."""
    if not text:
        return Markup("")

    text = normalize_newlines(text).strip()
    html_parts = []

    for raw_block in text.split("\n\n"):
        lines = [line.strip() for line in raw_block.split("\n") if line.strip()]
        if not lines:
            continue

        if lines[0].startswith("## "):
            title = lines[0][3:].strip()
            html_parts.append(f'<h2 class="font-display text-lg text-hi font-semibold mt-8 mb-2">{escape(title)}</h2>')
            body_html = _render_body_lines(lines[1:])
            if body_html:
                html_parts.append(body_html)
            continue

        html_parts.append(_render_body_lines(lines))

    return Markup("\n".join(html_parts))
