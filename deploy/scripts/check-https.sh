#!/usr/bin/env bash
# =============================================================
# check-https.sh — verifica o estado do HTTPS em produção:
# domínio configurado, validade do certificado, se a renovação
# automática está ativa e se o site realmente responde em HTTPS
# com o cadeado correto (sem avisos de segurança).
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
    need_cmd openssl
    PRIMARY_DOMAIN="$(echo "$SERVER_NAMES" | awk '{print $1}')"
    CERT_LIVE_DIR="/etc/letsencrypt/live/$PRIMARY_DOMAIN"
    CERT_FULLCHAIN="$CERT_LIVE_DIR/fullchain.pem"

    title "1) Certificado em disco"
    if [ -s "$CERT_FULLCHAIN" ]; then
        ok "Encontrado em $CERT_FULLCHAIN"
        openssl x509 -in "$CERT_FULLCHAIN" -noout -subject -issuer -enddate -ext subjectAltName 2>/dev/null | sed 's/^/  /'
    else
        err "Não encontrei certificado em $CERT_FULLCHAIN. Rode: sudo deploy/scripts/setup-nginx.sh $APP_DIR"
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
    if [ -x "/etc/letsencrypt/renewal-hooks/deploy/reload-nginx-midia-indoor.sh" ]; then
        ok "Hook de recarregar o Nginx após renovação está instalado."
    else
        warn "Hook de recarregar o Nginx após renovação NÃO está instalado."
        warn "Rode setup-nginx.sh novamente para instalá-lo (sem isso, um certificado renovado só entra em uso após reiniciar o Nginx manualmente)."
    fi

    if command -v certbot >/dev/null 2>&1; then
        title "3) Teste de renovação (--dry-run, não altera o certificado atual)"
        if certbot renew --cert-name "$PRIMARY_DOMAIN" --dry-run >/tmp/certbot-dry-run.log 2>&1; then
            ok "Simulação de renovação passou sem erros."
        else
            warn "Simulação de renovação falhou — veja /tmp/certbot-dry-run.log"
        fi
    fi

    title "4) Site respondendo em HTTPS"
    if curl -fsSk --max-time 8 -o /dev/null -w "HTTP %{http_code} — TLS: %{ssl_verify_result} (0 = válido)\n" "https://$PRIMARY_DOMAIN/healthz"; then
        ok "https://$PRIMARY_DOMAIN/healthz respondeu."
    else
        err "https://$PRIMARY_DOMAIN/healthz não respondeu. Confira: sudo systemctl status nginx midia-indoor"
    fi

    if curl -fsSkI --max-time 8 "https://$PRIMARY_DOMAIN/" 2>/dev/null | grep -qi '^strict-transport-security:'; then
        ok "Cabeçalho HSTS presente (o navegador vai lembrar de sempre usar HTTPS neste domínio)."
    else
        warn "Cabeçalho HSTS não encontrado na resposta — confira se o vhost ativo é o gerado por setup-nginx.sh."
    fi

    title "5) O Nginx está servindo o mesmo certificado que está em disco?"
    if [ -s "$CERT_FULLCHAIN" ]; then
        DISK_SERIAL="$(openssl x509 -in "$CERT_FULLCHAIN" -noout -serial 2>/dev/null | cut -d= -f2)"
        LIVE_CERT="$(echo | openssl s_client -servername "$PRIMARY_DOMAIN" -connect "$PRIMARY_DOMAIN:443" 2>/dev/null)"
        LIVE_SERIAL="$(echo "$LIVE_CERT" | openssl x509 -noout -serial 2>/dev/null | cut -d= -f2)"
        EXPIRY="$(echo "$LIVE_CERT" | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)"
        if [ -z "$LIVE_SERIAL" ]; then
            warn "Não consegui ler o certificado via TLS (firewall bloqueando a porta 443 a partir daqui, ou o Nginx não está escutando em 443?)."
        elif [ "$DISK_SERIAL" = "$LIVE_SERIAL" ]; then
            ok "Confirmado: o Nginx está servindo exatamente o certificado válido em disco (série $DISK_SERIAL)."
            [ -n "$EXPIRY" ] && ok "Válido até: $EXPIRY"
        else
            err "MISMATCH: o certificado servido pelo Nginx (série $LIVE_SERIAL) é diferente do que está em disco (série $DISK_SERIAL)."
            err "Esta é a causa mais comum do navegador mostrar o domínio como 'não seguro'/com aviso mesmo com um certificado válido instalado."
            err "Possíveis causas: outro vhost concorrente na porta 443, cache do navegador de uma visita anterior, ou CDN/proxy na frente do servidor servindo um certificado diferente."
            err "Rode: sudo nginx -T | grep -A2 'listen 443'   para ver todos os vhosts que escutam 443."
        fi
    fi

    title "6) Conteúdo misto (recursos http:// numa página https://)"
    MIXED="$(curl -fsSk --max-time 8 "https://$PRIMARY_DOMAIN/" 2>/dev/null | grep -oE 'src="http://[^"]+"|href="http://[^"]+"' | grep -v "$PRIMARY_DOMAIN" | head -5 || true)"
    if [ -n "$MIXED" ]; then
        warn "Encontrado conteúdo misto na página inicial (causa o cadeado 'quebrado'/com aviso):"
        echo "$MIXED" | sed 's/^/    /'
    else
        ok "Nenhum recurso http:// óbvio encontrado na página inicial."
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
