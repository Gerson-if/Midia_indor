#!/usr/bin/env bash
# =============================================================
# setup-nginx.sh — gera e ativa o vhost do Nginx a partir do
# deploy/nginx.conf.template, usando os dados do .env (ou
# perguntando novamente se preferir reconfigurar).
#
# Uso:
#   sudo deploy/scripts/setup-nginx.sh [/opt/midia-indoor]
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root
need_cmd nginx

APP_DIR="${1:-/opt/midia-indoor}"
ENV_FILE="$APP_DIR/shared/.env"
TEMPLATE="$SCRIPT_DIR/../nginx.conf.template"
SITE_NAME="midia-indoor"
SITE_AVAILABLE="/etc/nginx/sites-available/$SITE_NAME"
SITE_ENABLED="/etc/nginx/sites-enabled/$SITE_NAME"

[ -f "$ENV_FILE" ] || die "Não encontrei $ENV_FILE. Rode primeiro o install.sh ou configure-env.sh."

# shellcheck disable=SC1090
source <(grep -E '^(SERVER_NAMES|USE_HTTPS|LETSENCRYPT_EMAIL|MAX_CONTENT_LENGTH_MB|GUNICORN_BIND)=' "$ENV_FILE" | sed 's/^/export /')

SERVER_NAMES="${SERVER_NAMES:-_}"
SERVER_NAMES="${SERVER_NAMES//\"/}"
USE_HTTPS="${USE_HTTPS:-0}"
MAX_UPLOAD_MB="${MAX_CONTENT_LENGTH_MB:-80}"
GUNICORN_BIND="${GUNICORN_BIND:-127.0.0.1:8000}"
STATIC_PATH="$APP_DIR/current/app/static"

title "Gerando configuração do Nginx"
info "server_name: $SERVER_NAMES"
info "HTTPS via Let's Encrypt: $([ "$USE_HTTPS" = "1" ] && echo sim || echo não)"

mkdir -p /var/www/certbot

sed \
    -e "s#__SERVER_NAMES__#${SERVER_NAMES}#g" \
    -e "s#__STATIC_PATH__#${STATIC_PATH}#g" \
    -e "s#__GUNICORN_BIND__#${GUNICORN_BIND}#g" \
    -e "s#__MAX_UPLOAD_MB__#${MAX_UPLOAD_MB}#g" \
    "$TEMPLATE" >"$SITE_AVAILABLE"

ln -sf "$SITE_AVAILABLE" "$SITE_ENABLED"

# Remove o site padrão do Nginx se ainda estiver ativo (evita conflito de porta 80)
[ -e /etc/nginx/sites-enabled/default ] && rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl reload nginx
ok "Nginx configurado e recarregado (HTTP)."

if [ "$USE_HTTPS" = "1" ]; then
    if [ "$SERVER_NAMES" = "_" ]; then
        warn "Sem domínio configurado — pulando emissão de certificado HTTPS."
    else
        need_cmd certbot
        title "Emitindo certificado HTTPS (Let's Encrypt)"
        DOMAIN_ARGS=()
        for d in $SERVER_NAMES; do
            DOMAIN_ARGS+=(-d "$d")
        done
        EMAIL_ARG=()
        if [ -n "${LETSENCRYPT_EMAIL:-}" ]; then
            EMAIL_ARG=(-m "$LETSENCRYPT_EMAIL")
        else
            EMAIL_ARG=(--register-unsafely-without-email)
        fi
        if certbot --nginx "${DOMAIN_ARGS[@]}" "${EMAIL_ARG[@]}" --agree-tos --redirect --non-interactive; then
            ok "Certificado HTTPS emitido e Nginx atualizado automaticamente pelo Certbot."
            ok "Renovação automática já fica agendada pelo systemd timer do certbot (certbot.timer)."
        else
            warn "Falha ao emitir certificado. O site continua funcionando em HTTP."
            warn "Verifique se o domínio já aponta (registro DNS tipo A) para o IP desta VPS e tente novamente:"
            warn "  sudo certbot --nginx ${DOMAIN_ARGS[*]}"
        fi
    fi
fi

nginx -t && systemctl reload nginx
ok "Nginx pronto."
