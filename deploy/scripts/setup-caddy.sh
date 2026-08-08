#!/usr/bin/env bash
# =============================================================
# setup-caddy.sh — instala o Caddy (se necessário) e gera o
# Caddyfile a partir de deploy/Caddyfile.template.
#
# Diferente do antigo setup-nginx.sh, aqui não existe "modo" a
# escolher (letsencrypt/selfsigned/custom): o Caddy emite HTTPS
# automaticamente, sob demanda, para qualquer domínio validado
# pela própria aplicação (GET /internal/domain-check) -- inclusive
# para páginas cadastradas DEPOIS desta instalação, pelo painel do
# super admin, sem precisar rodar este script de novo.
#
# Uso:
#   sudo deploy/scripts/setup-caddy.sh [/opt/midia-indoor]
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root

APP_DIR="${1:-/opt/midia-indoor}"
ENV_FILE="$APP_DIR/.env"
TEMPLATE="$SCRIPT_DIR/../Caddyfile.template"
CADDYFILE="/etc/caddy/Caddyfile"

[ -f "$TEMPLATE" ] || die "Template não encontrado: $TEMPLATE (o projeto está incompleto/corrompido?)"
[ -f "$ENV_FILE" ] || die "Não encontrei $ENV_FILE. Rode primeiro o install.sh ou configure-env.sh."

# ---------------------------------------------------------------
# 1) Instala o Caddy via repositório oficial, se ainda não estiver.
# ---------------------------------------------------------------
if ! command -v caddy >/dev/null 2>&1; then
    info "Instalando o Caddy (repositório oficial)..."
    apt-get install -y --no-install-recommends debian-keyring debian-archive-keyring apt-transport-https curl gnupg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -y
    apt-get install -y --no-install-recommends caddy
    ok "Caddy instalado."
else
    ok "Caddy já está instalado ($(caddy version 2>/dev/null | head -n1))."
fi

mkdir -p /var/log/caddy
chown caddy:caddy /var/log/caddy 2>/dev/null || true

# ---------------------------------------------------------------
# 2) Lê variáveis do .env necessárias para o Caddyfile
# ---------------------------------------------------------------
env_value() {
    # Lê uma variável do .env sem dar source nele (evita executar
    # conteúdo arbitrário do arquivo).
    local key="$1" default="${2:-}"
    local line
    line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n1 || true)"
    if [ -z "$line" ]; then
        echo "$default"
        return
    fi
    echo "${line#*=}"
}

GUNICORN_BIND="$(env_value GUNICORN_BIND "127.0.0.1:8000")"
ASK_PORT="${GUNICORN_BIND##*:}"
STATIC_PATH="$APP_DIR/app/static"

ACME_EMAIL="$(env_value ACME_EMAIL "")"
if [ -z "$ACME_EMAIL" ]; then
    ask "E-mail para avisos do Let's Encrypt (renovação/expiração de certificados)" "" ACME_EMAIL
fi

# ---------------------------------------------------------------
# 3) Gera o Caddyfile a partir do template (com backup automático)
# ---------------------------------------------------------------
if [ -f "$CADDYFILE" ]; then
    cp "$CADDYFILE" "${CADDYFILE}.bak"
fi

sed \
    -e "s#__ACME_EMAIL__#${ACME_EMAIL}#g" \
    -e "s#__ASK_PORT__#${ASK_PORT}#g" \
    -e "s#__STATIC_PATH__#${STATIC_PATH}#g" \
    -e "s#__GUNICORN_BIND__#${GUNICORN_BIND}#g" \
    "$TEMPLATE" > "$CADDYFILE"

if caddy validate --config "$CADDYFILE" >/dev/null 2>&1; then
    systemctl enable caddy >/dev/null 2>&1 || true
    systemctl reload caddy 2>/dev/null || systemctl restart caddy
    ok "Caddy configurado e recarregado — HTTPS automático ativo para qualquer domínio cadastrado no painel do super admin."
else
    if [ -f "${CADDYFILE}.bak" ]; then
        mv "${CADDYFILE}.bak" "$CADDYFILE"
        err "O novo Caddyfile não passou na validação — a versão anterior foi restaurada. Rode 'caddy validate --config $CADDYFILE' para ver o detalhe do erro."
    else
        err "O novo Caddyfile não passou na validação. Rode 'caddy validate --config $CADDYFILE' para ver o detalhe do erro."
    fi
    exit 1
fi

info "Portas 80/443 abertas? Confira 'ufw status' (ou o firewall do provedor da VPS) se o acesso externo não funcionar."
info "Para cada domínio novo cadastrado depois pelo painel /superadmin, basta apontar o DNS (registro A) para o IP desta VPS — nenhum passo aqui precisa ser repetido."
