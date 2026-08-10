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
    retry 3 5 apt-get install -y --no-install-recommends debian-keyring debian-archive-keyring apt-transport-https curl gnupg
    retry 3 5 bash -c "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg"
    retry 3 5 bash -c "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list"
    retry 3 5 apt-get update -y
    retry 3 5 apt-get install -y --no-install-recommends caddy
    command -v caddy >/dev/null 2>&1 || die "Instalação do Caddy falhou — confira 'apt-get install caddy' manualmente e a conectividade com dl.cloudsmith.io."
    ok "Caddy instalado ($(caddy version 2>/dev/null | head -n1))."
else
    ok "Caddy já está instalado ($(caddy version 2>/dev/null | head -n1))."
fi

# on_demand_tls -> permission http (usado no template) só existe a
# partir do Caddy 2.10 — se por algum motivo uma versão mais antiga
# estiver instalada (ex.: pacote em cache/mirror desatualizado), o
# validate abaixo vai falhar; avisamos a causa mais provável antes.
CADDY_VERSION="$(caddy version 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | head -n1 | tr -d 'v')"
if [ -n "$CADDY_VERSION" ]; then
    CADDY_MAJOR="${CADDY_VERSION%%.*}"
    CADDY_MINOR="$(echo "$CADDY_VERSION" | cut -d. -f2)"
    if [ "$CADDY_MAJOR" -lt 2 ] || { [ "$CADDY_MAJOR" -eq 2 ] && [ "$CADDY_MINOR" -lt 10 ]; }; then
        warn "Caddy $CADDY_VERSION detectado — este template usa 'permission http', disponível a partir do Caddy 2.10. Rode 'sudo apt-get update && sudo apt-get install --only-upgrade caddy' antes de continuar."
    fi
fi

mkdir -p /var/log/caddy
# -R (recursivo) é essencial aqui: se essa pasta já existia com algum
# arquivo de dono 'root' (de uma tentativa anterior manual, ou de uma
# instalação anterior que rodou o Caddy de outro jeito), um chown só
# no diretório NÃO alcança esse arquivo — e o Caddy (que roda como o
# usuário de sistema 'caddy', não root) falha ao abrir esse arquivo
# de log específico com 'permission denied', mesmo com a pasta em si
# já pertencendo a 'caddy'. Também não silenciamos mais o erro (antes
# tinha 2>/dev/null || true): se isso falhar, é melhor avisar agora
# do que descobrir só quando o serviço não subir.
if ! chown -R caddy:caddy /var/log/caddy; then
    warn "Não consegui ajustar o dono de /var/log/caddy para o usuário 'caddy' (ele existe? confira com 'id caddy'). O Caddy pode falhar ao tentar escrever o log de acesso."
fi

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

# ACME_EMAIL é o nome "canônico" desta variável, mas configure-env.sh
# (e instalações mais antigas) podem ter gravado apenas LETSENCRYPT_EMAIL,
# ADMIN_EMAIL ou COMPANY_EMAIL — antes disso ser corrigido, essa
# diferença de nome fazia o Caddy pedir o e-mail de novo TODA vez que
# este script rodava, mesmo já tendo sido informado no install.sh.
ACME_EMAIL="$(env_value ACME_EMAIL "")"
[ -z "$ACME_EMAIL" ] && ACME_EMAIL="$(env_value LETSENCRYPT_EMAIL "")"
[ -z "$ACME_EMAIL" ] && ACME_EMAIL="$(env_value ADMIN_EMAIL "")"
[ -z "$ACME_EMAIL" ] && ACME_EMAIL="$(env_value COMPANY_EMAIL "")"
if [ -z "$ACME_EMAIL" ]; then
    ask_validated "E-mail para avisos do Let's Encrypt (renovação/expiração de certificados)" "" ACME_EMAIL \
        is_valid_email "E-mail com formato inválido"
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

if ! caddy validate --config "$CADDYFILE" >/dev/null 2>&1; then
    VALIDATE_OUTPUT="$(caddy validate --config "$CADDYFILE" 2>&1 || true)"
    if [ -f "${CADDYFILE}.bak" ]; then
        mv "${CADDYFILE}.bak" "$CADDYFILE"
        err "O novo Caddyfile não passou na validação — a versão anterior foi restaurada."
    else
        err "O novo Caddyfile não passou na validação."
    fi
    err "Detalhe: $VALIDATE_OUTPUT"
    exit 1
fi

systemctl enable caddy >/dev/null 2>&1 || true
systemctl reload caddy 2>/dev/null || systemctl restart caddy

# Validar o arquivo é necessário mas não suficiente: o processo pode
# não subir por outro motivo (porta 80/443 já ocupada, permissão de
# arquivo, etc.) — confirmamos que o serviço realmente está ativo.
sleep 2
if ! systemctl is-active --quiet caddy; then
    err "O Caddyfile é válido, mas o serviço 'caddy' não ficou ativo. Verifique: sudo journalctl -u caddy -n 50"
    exit 1
fi
rm -f "${CADDYFILE}.bak"
ok "Caddy configurado e recarregado — HTTPS automático ativo para qualquer domínio cadastrado no painel do super admin."

info "Portas 80/443 abertas? Confira 'ufw status' (ou o firewall do provedor da VPS) se o acesso externo não funcionar."
info "Para cada domínio novo cadastrado depois pelo painel /superadmin, basta apontar o DNS (registro A) para o IP desta VPS — nenhum passo aqui precisa ser repetido."
