#!/usr/bin/env bash
# =============================================================
# check-https.sh — verifica o estado do HTTPS em produção:
# domínio configurado, validade do certificado, se a renovação
# automática está ativa e se o site realmente responde em HTTPS.
#
# Uso:
#   sudo deploy/scripts/check-https.sh [/opt/midia-indoor]
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

APP_DIR="${1:-/opt/midia-indoor}"
ENV_FILE="$APP_DIR/.env"

[ -f "$ENV_FILE" ] || die "Não encontrei $ENV_FILE."

# shellcheck disable=SC1090
source <(grep -E '^(SERVER_NAMES|USE_HTTPS|SSL_MODE)=' "$ENV_FILE" | sed 's/^/export /')
SERVER_NAMES="${SERVER_NAMES//\"/}"
SSL_MODE="${SSL_MODE:-}"
[ -z "$SSL_MODE" ] && SSL_MODE="desconhecido (arquivo .env antigo)"

title "Estado do HTTPS — $APP_DIR"
info "server_name(s): $SERVER_NAMES"
info "Modo (SSL_MODE): $SSL_MODE"
echo

case "$SSL_MODE" in
letsencrypt)
    need_cmd certbot
    PRIMARY_DOMAIN="$(echo "$SERVER_NAMES" | awk '{print $1}')"

    title "1) Certificado (Certbot)"
    if certbot certificates --cert-name "$PRIMARY_DOMAIN" 2>/dev/null | grep -q "Certificate Name:"; then
        certbot certificates --cert-name "$PRIMARY_DOMAIN" 2>/dev/null | sed -n '/Certificate Name:/,/Certificate Path:/p'
    else
        warn "Não encontrei um certificado do Certbot para '$PRIMARY_DOMAIN'. Rode setup-nginx.sh para emitir."
    fi

    title "2) Renovação automática"
    if systemctl list-unit-files 2>/dev/null | grep -q '^certbot.timer'; then
        if systemctl is-active --quiet certbot.timer; then
            ok "certbot.timer está ativo."
            systemctl list-timers certbot.timer --no-pager 2>/dev/null | head -3
        else
            warn "certbot.timer existe mas está INATIVO. Ative com: sudo systemctl enable --now certbot.timer"
        fi
    else
        warn "certbot.timer não encontrado neste sistema."
    fi

    title "3) Teste de renovação (--dry-run, não altera o certificado atual)"
    if certbot renew --cert-name "$PRIMARY_DOMAIN" --dry-run >/tmp/certbot-dry-run.log 2>&1; then
        ok "Simulação de renovação passou sem erros."
    else
        warn "Simulação de renovação falhou — veja /tmp/certbot-dry-run.log"
    fi

    title "4) Site respondendo em HTTPS"
    if curl -fsSk --max-time 8 -o /dev/null -w "HTTP %{http_code} — TLS: %{ssl_verify_result} (0 = válido)\n" "https://$PRIMARY_DOMAIN/healthz"; then
        ok "https://$PRIMARY_DOMAIN/healthz respondeu."
    else
        err "https://$PRIMARY_DOMAIN/healthz não respondeu. Confira: sudo systemctl status nginx midia-indoor"
    fi

    title "5) Data de validade do certificado (via TLS, direto do domínio)"
    if command -v openssl >/dev/null 2>&1; then
        EXPIRY="$(echo | openssl s_client -servername "$PRIMARY_DOMAIN" -connect "$PRIMARY_DOMAIN:443" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)"
        if [ -n "$EXPIRY" ]; then
            ok "Válido até: $EXPIRY"
        else
            warn "Não consegui ler a validade via TLS (firewall bloqueando 443 a partir daqui?)."
        fi
    fi
    ;;

selfsigned)
    SSL_DIR="/etc/nginx/ssl/midia-indoor"
    SSL_CERT="$SSL_DIR/fullchain.pem"

    title "1) Certificado autoassinado"
    if [ -s "$SSL_CERT" ]; then
        ok "Encontrado em $SSL_CERT"
        need_cmd openssl
        openssl x509 -in "$SSL_CERT" -noout -subject -enddate -ext subjectAltName 2>/dev/null | sed 's/^/  /'
    else
        err "Certificado não encontrado em $SSL_CERT. Rode: sudo deploy/scripts/setup-nginx.sh $APP_DIR"
    fi

    title "2) Site respondendo em HTTPS (aviso de segurança do navegador é esperado, sem domínio)"
    PRIMARY="$(echo "$SERVER_NAMES" | awk '{print $1}')"
    if curl -fsSk --max-time 8 -o /dev/null -w "HTTP %{http_code}\n" "https://$PRIMARY/healthz"; then
        ok "https://$PRIMARY/healthz respondeu (certificado não validado por CA pública, e tudo bem — é o modo autoassinado)."
    else
        err "https://$PRIMARY/healthz não respondeu. Confira: sudo systemctl status nginx midia-indoor"
    fi

    info "Quando tiver domínio, rode configure-env.sh + setup-nginx.sh de novo para trocar pelo Let's Encrypt."
    ;;

*)
    warn "HTTPS não está ativo (SSL_MODE=$SSL_MODE). O site responde apenas em HTTP."
    info "Para ativar: sudo bash deploy/scripts/configure-env.sh $ENV_FILE && sudo bash deploy/scripts/setup-nginx.sh $APP_DIR"
    ;;
esac

echo
ok "Verificação concluída."
