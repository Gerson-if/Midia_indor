#!/usr/bin/env bash
# =============================================================
# setup-nginx.sh — gera e ativa o vhost do Nginx a partir dos
# templates em deploy/*.conf.template, usando os dados do .env
# (ou perguntando novamente se preferir reconfigurar).
#
# Modos suportados (variável SSL_MODE no .env):
#   - "letsencrypt": domínio + certificado público via Certbot
#   - "selfsigned" : sem domínio (acesso por IP) + certificado
#                    autoassinado gerado localmente (openssl)
#   - "none"       : HTTP simples, sem HTTPS
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
ENV_FILE="$APP_DIR/.env"
TEMPLATE_HTTP="$SCRIPT_DIR/../nginx.conf.template"
TEMPLATE_SELFSIGNED="$SCRIPT_DIR/../nginx-selfsigned.conf.template"
SITE_NAME="midia-indoor"
SITE_AVAILABLE="/etc/nginx/sites-available/$SITE_NAME"
SITE_ENABLED="/etc/nginx/sites-enabled/$SITE_NAME"
SSL_DIR="/etc/nginx/ssl/midia-indoor"
SSL_CERT="$SSL_DIR/fullchain.pem"
SSL_KEY="$SSL_DIR/privkey.pem"

[ -f "$ENV_FILE" ] || die "Não encontrei $ENV_FILE. Rode primeiro o install.sh ou configure-env.sh."

# shellcheck disable=SC1090
source <(grep -E '^(SERVER_NAMES|USE_HTTPS|SSL_MODE|LETSENCRYPT_EMAIL|MAX_CONTENT_LENGTH_MB|GUNICORN_BIND)=' "$ENV_FILE" | sed 's/^/export /')

SERVER_NAMES="${SERVER_NAMES:-_}"
SERVER_NAMES="${SERVER_NAMES//\"/}"
USE_HTTPS="${USE_HTTPS:-0}"
SSL_MODE="${SSL_MODE:-}"

# Compatibilidade com .env antigos, gerados antes de existir SSL_MODE:
# deduz o modo a partir do USE_HTTPS + se há domínio configurado.
if [ -z "$SSL_MODE" ]; then
    if [ "$USE_HTTPS" = "1" ] && [ "$SERVER_NAMES" != "_" ]; then
        SSL_MODE="letsencrypt"
    else
        SSL_MODE="none"
    fi
fi

MAX_UPLOAD_MB="${MAX_CONTENT_LENGTH_MB:-80}"
GUNICORN_BIND="${GUNICORN_BIND:-127.0.0.1:8000}"
STATIC_PATH="$APP_DIR/app/static"

title "Gerando configuração do Nginx"
info "server_name: $SERVER_NAMES"
case "$SSL_MODE" in
    letsencrypt) info "HTTPS: Let's Encrypt (domínio público)" ;;
    selfsigned)  info "HTTPS: certificado autoassinado (acesso por IP)" ;;
    *)           info "HTTPS: desativado (HTTP simples)" ;;
esac

mkdir -p /var/www/certbot

if [ "$SSL_MODE" = "selfsigned" ]; then
    need_cmd openssl
    mkdir -p "$SSL_DIR"
    if [ -s "$SSL_CERT" ] && [ -s "$SSL_KEY" ]; then
        ok "Certificado autoassinado já existe em $SSL_DIR — reaproveitando (não regera a cada deploy)."
    else
        title "Gerando certificado autoassinado (válido por 10 anos)"
        SAN_ENTRIES=""
        for name in $SERVER_NAMES; do
            [ "$name" = "_" ] && continue
            if is_ipv4 "$name"; then
                SAN_ENTRIES="${SAN_ENTRIES}IP:${name},"
            else
                SAN_ENTRIES="${SAN_ENTRIES}DNS:${name},"
            fi
        done
        SAN_ENTRIES="${SAN_ENTRIES%,}"
        [ -z "$SAN_ENTRIES" ] && SAN_ENTRIES="IP:127.0.0.1"
        CN_NAME="$(echo "$SERVER_NAMES" | awk '{print $1}')"
        [ "$CN_NAME" = "_" ] && CN_NAME="localhost"

        openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
            -keyout "$SSL_KEY" -out "$SSL_CERT" \
            -subj "/CN=${CN_NAME}" \
            -addext "subjectAltName=${SAN_ENTRIES}" >/dev/null 2>&1

        chmod 600 "$SSL_KEY"
        ok "Certificado gerado em $SSL_DIR (cobre: $SAN_ENTRIES)."
    fi

    sed \
        -e "s#__SERVER_NAMES__#${SERVER_NAMES}#g" \
        -e "s#__STATIC_PATH__#${STATIC_PATH}#g" \
        -e "s#__GUNICORN_BIND__#${GUNICORN_BIND}#g" \
        -e "s#__MAX_UPLOAD_MB__#${MAX_UPLOAD_MB}#g" \
        -e "s#__SSL_CERT__#${SSL_CERT}#g" \
        -e "s#__SSL_KEY__#${SSL_KEY}#g" \
        "$TEMPLATE_SELFSIGNED" >"$SITE_AVAILABLE"
else
    sed \
        -e "s#__SERVER_NAMES__#${SERVER_NAMES}#g" \
        -e "s#__STATIC_PATH__#${STATIC_PATH}#g" \
        -e "s#__GUNICORN_BIND__#${GUNICORN_BIND}#g" \
        -e "s#__MAX_UPLOAD_MB__#${MAX_UPLOAD_MB}#g" \
        "$TEMPLATE_HTTP" >"$SITE_AVAILABLE"
fi

ln -sf "$SITE_AVAILABLE" "$SITE_ENABLED"

# Remove o site padrão do Nginx se ainda estiver ativo (evita conflito de porta 80)
[ -e /etc/nginx/sites-enabled/default ] && rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl reload nginx

case "$SSL_MODE" in
    selfsigned)
        ok "Nginx configurado e recarregado — HTTPS ativo (porta 443) com certificado autoassinado."
        warn "O navegador vai avisar que a conexão 'não é privada'/certificado inválido na primeira visita — é esperado, pois não há domínio validado por uma autoridade pública. A conexão continua criptografada; basta confirmar o aviso."
        ;;
    letsencrypt)
        ok "Nginx configurado e recarregado (HTTP)."
        ;;
    *)
        ok "Nginx configurado e recarregado (HTTP)."
        ;;
esac

if [ "$SSL_MODE" = "letsencrypt" ]; then
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
