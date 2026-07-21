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
#   - "custom"     : certificado comprado de uma CA (DigiCert,
#                    Sectigo, etc.) via CSR — veja generate-csr.sh
#   - "none"       : HTTP simples, sem HTTPS
#
# Diferença importante em relação a versões anteriores:
# no modo "letsencrypt" o Certbot NÃO edita mais o nginx.conf
# diretamente (não usamos mais `certbot --nginx`). Em vez disso:
#   1. o Certbot só emite/renova o certificado (`certbot certonly`);
#   2. o bloco HTTPS do Nginx vem do nosso próprio template
#      (nginx-letsencrypt.conf.template), sempre reaplicado.
# Isso evita o principal motivo do cadeado "sumir": reexecuções
# deste script apagando o bloco SSL que o certbot havia inserido.
#
# Toda alteração no vhost é feita com backup automático: se a nova
# configuração não passar em `nginx -t`, a versão anterior (que
# funcionava) é restaurada e o site nunca fica fora do ar por causa
# de um erro deste script.
#
# Uso:
#   sudo deploy/scripts/setup-nginx.sh [/opt/midia-indoor]
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

on_error() {
    local line="$1"
    err "Falha inesperada em setup-nginx.sh (linha $line)."
    err "Nada foi deixado pela metade de propósito: se um vhost já estava"
    err "funcionando antes, ele continua ativo. Rode novamente depois de"
    err "corrigir o problema indicado acima, ou 'nginx -t' para detalhes."
}
trap 'on_error $LINENO' ERR

need_root
need_cmd nginx
need_cmd curl
need_cmd awk
need_cmd sed

APP_DIR="${1:-/opt/midia-indoor}"
ENV_FILE="$APP_DIR/.env"
TEMPLATE_HTTP="$SCRIPT_DIR/../nginx.conf.template"
TEMPLATE_SELFSIGNED="$SCRIPT_DIR/../nginx-selfsigned.conf.template"
TEMPLATE_LETSENCRYPT="$SCRIPT_DIR/../nginx-letsencrypt.conf.template"
TEMPLATE_CUSTOM="$SCRIPT_DIR/../nginx-custom.conf.template"
SITE_NAME="midia-indoor"
SITE_AVAILABLE="/etc/nginx/sites-available/$SITE_NAME"
SITE_ENABLED="/etc/nginx/sites-enabled/$SITE_NAME"
SITE_BACKUP="/etc/nginx/sites-available/${SITE_NAME}.bak"
SSL_DIR="/etc/nginx/ssl/midia-indoor"
SSL_CERT="$SSL_DIR/fullchain.pem"
SSL_KEY="$SSL_DIR/privkey.pem"

for tpl in "$TEMPLATE_HTTP" "$TEMPLATE_SELFSIGNED" "$TEMPLATE_LETSENCRYPT" "$TEMPLATE_CUSTOM"; do
    [ -f "$tpl" ] || die "Template não encontrado: $tpl (o projeto está incompleto/corrompido?)"
done

[ -f "$ENV_FILE" ] || die "Não encontrei $ENV_FILE. Rode primeiro o install.sh ou configure-env.sh."

# shellcheck disable=SC1090
source <(grep -E '^(SERVER_NAMES|USE_HTTPS|SSL_MODE|LETSENCRYPT_EMAIL|MAX_CONTENT_LENGTH_MB|GUNICORN_BIND|CUSTOM_SSL_CERT|CUSTOM_SSL_KEY|CUSTOM_SSL_CHAIN)=' "$ENV_FILE" | sed 's/^/export /')

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

if [ "$SSL_MODE" = "letsencrypt" ] && [ "$SERVER_NAMES" = "_" ]; then
    warn "SSL_MODE=letsencrypt mas não há domínio configurado (SERVER_NAMES=_)."
    warn "Let's Encrypt exige um domínio público — caindo para HTTP simples."
    warn "Rode configure-env.sh e informe um domínio, ou escolha o modo autoassinado."
    SSL_MODE="none"
fi

CUSTOM_SSL_CERT="${CUSTOM_SSL_CERT:-}"
CUSTOM_SSL_KEY="${CUSTOM_SSL_KEY:-}"
CUSTOM_SSL_CHAIN="${CUSTOM_SSL_CHAIN:-}"
if [ "$SSL_MODE" = "custom" ]; then
    if [ -z "$CUSTOM_SSL_CERT" ] || [ -z "$CUSTOM_SSL_KEY" ]; then
        warn "SSL_MODE=custom mas CUSTOM_SSL_CERT/CUSTOM_SSL_KEY não estão definidos no .env."
        warn "Rode configure-env.sh e informe os caminhos do certificado comprado — caindo para HTTP simples por enquanto."
        SSL_MODE="none"
    fi
fi

MAX_UPLOAD_MB="${MAX_CONTENT_LENGTH_MB:-80}"
GUNICORN_BIND="${GUNICORN_BIND:-127.0.0.1:8000}"
STATIC_PATH="$APP_DIR/app/static"
PRIMARY_DOMAIN="$(echo "$SERVER_NAMES" | awk '{print $1}')"

title "Gerando configuração do Nginx"
info "server_name: $SERVER_NAMES"
case "$SSL_MODE" in
    letsencrypt) info "HTTPS: Let's Encrypt (domínio público)" ;;
    selfsigned)  info "HTTPS: certificado autoassinado (acesso por IP)" ;;
    custom)      info "HTTPS: certificado comprado via CSR (manual)" ;;
    *)           info "HTTPS: desativado (HTTP simples)" ;;
esac

mkdir -p /var/www/certbot

# ---- Detecta suporte a `http2 on;` (Nginx >= 1.25.1) para evitar
#      `nginx -t` falhar em servidores com versões mais antigas ----
detect_http2_syntax() {
    local ver
    ver="$(nginx -v 2>&1 | sed -n 's#.*nginx/\([0-9.]*\).*#\1#p')"
    if [ -z "$ver" ]; then
        echo "legacy"
        return
    fi
    local major minor patch
    IFS='.' read -r major minor patch <<<"$ver"
    if [ "${major:-0}" -gt 1 ] 2>/dev/null; then
        echo "modern"; return
    fi
    if [ "${major:-0}" -eq 1 ] && [ "${minor:-0}" -gt 25 ] 2>/dev/null; then
        echo "modern"; return
    fi
    if [ "${major:-0}" -eq 1 ] && [ "${minor:-0}" -eq 25 ] && [ "${patch:-0}" -ge 1 ] 2>/dev/null; then
        echo "modern"; return
    fi
    echo "legacy"
}

# Aplica a sintaxe de HTTP/2 correta a um arquivo de config já gerado.
apply_http2_compat() {
    local file="$1"
    local syntax
    syntax="$(detect_http2_syntax)"
    if [ "$syntax" = "modern" ]; then
        return 0
    fi
    # Servidor com Nginx antigo: remove a diretiva "http2 on;" (não
    # existe nessas versões) e usa a forma legada "listen ... ssl http2;"
    sed -i \
        -e '/^\s*http2 on;\s*$/d' \
        -e 's/^\(\s*\)listen 443 ssl;$/\1listen 443 ssl http2;/' \
        -e 's/^\(\s*\)listen \[::\]:443 ssl;$/\1listen [::]:443 ssl http2;/' \
        "$file"
}

# Escreve um novo vhost com segurança: guarda backup do que já
# funcionava e só substitui de fato se `nginx -t` aprovar o novo.
# Uso: safe_deploy_site <arquivo_gerado_temporario>
safe_deploy_site() {
    local new_conf="$1"
    if [ -s "$SITE_AVAILABLE" ]; then
        cp -f "$SITE_AVAILABLE" "$SITE_BACKUP"
    fi
    cp -f "$new_conf" "$SITE_AVAILABLE"
    ln -sf "$SITE_AVAILABLE" "$SITE_ENABLED"
    [ -e /etc/nginx/sites-enabled/default ] && rm -f /etc/nginx/sites-enabled/default

    if nginx -t 2>/tmp/nginx-test.log; then
        systemctl reload nginx
        return 0
    fi

    err "A nova configuração do Nginx tem erro — veja /tmp/nginx-test.log."
    if [ -s "$SITE_BACKUP" ]; then
        warn "Restaurando a configuração anterior (que estava funcionando) para não derrubar o site."
        cp -f "$SITE_BACKUP" "$SITE_AVAILABLE"
        ln -sf "$SITE_AVAILABLE" "$SITE_ENABLED"
        nginx -t && systemctl reload nginx
    fi
    return 1
}

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

    TMP_CONF="$(mktemp)"
    sed \
        -e "s#__SERVER_NAMES__#${SERVER_NAMES}#g" \
        -e "s#__STATIC_PATH__#${STATIC_PATH}#g" \
        -e "s#__GUNICORN_BIND__#${GUNICORN_BIND}#g" \
        -e "s#__MAX_UPLOAD_MB__#${MAX_UPLOAD_MB}#g" \
        -e "s#__SSL_CERT__#${SSL_CERT}#g" \
        -e "s#__SSL_KEY__#${SSL_KEY}#g" \
        "$TEMPLATE_SELFSIGNED" >"$TMP_CONF"

    if safe_deploy_site "$TMP_CONF"; then
        ok "Nginx configurado e recarregado — HTTPS ativo (porta 443) com certificado autoassinado."
        warn "O navegador vai avisar que a conexão 'não é privada'/certificado inválido na primeira visita — é esperado, pois não há domínio validado por uma autoridade pública. A conexão continua criptografada; basta confirmar o aviso."
    else
        rm -f "$TMP_CONF"
        die "Não foi possível ativar o Nginx com o certificado autoassinado. Veja /tmp/nginx-test.log."
    fi
    rm -f "$TMP_CONF"

elif [ "$SSL_MODE" = "custom" ]; then
    need_cmd openssl
    title "Instalando certificado comprado (CSR / autoridade certificadora)"

    [ -s "$CUSTOM_SSL_CERT" ] || die "Certificado não encontrado em: $CUSTOM_SSL_CERT (confira o caminho em $ENV_FILE / configure-env.sh)."
    [ -s "$CUSTOM_SSL_KEY" ]  || die "Chave privada não encontrada em: $CUSTOM_SSL_KEY (confira o caminho em $ENV_FILE / configure-env.sh)."

    # ---- 1) A chave privada realmente pertence a este certificado? ----
    # Causa clássica de erro silencioso no navegador (ou do Nginx nem subir).
    CERT_MODULUS="$(openssl x509 -in "$CUSTOM_SSL_CERT" -noout -modulus 2>/dev/null | openssl md5 2>/dev/null || true)"
    KEY_MODULUS="$(openssl rsa -in "$CUSTOM_SSL_KEY" -noout -modulus 2>/dev/null | openssl md5 2>/dev/null || true)"
    if [ -z "$CERT_MODULUS" ] || [ -z "$KEY_MODULUS" ]; then
        die "Não consegui ler o certificado e/ou a chave com openssl — confira se os arquivos estão no formato PEM correto."
    fi
    if [ "$CERT_MODULUS" != "$KEY_MODULUS" ]; then
        die "A chave privada ($CUSTOM_SSL_KEY) NÃO corresponde a este certificado ($CUSTOM_SSL_CERT). Isso por si só já faz o navegador recusar a conexão / mostrar aviso vermelho. Confira se você não trocou os arquivos, ou se a chave é a mesma usada para gerar o CSR (generate-csr.sh)."
    fi
    ok "Confirmado: a chave privada corresponde ao certificado."

    # ---- 2) O certificado cobre o(s) domínio(s) configurado(s)? ----
    CERT_NAMES="$(openssl x509 -in "$CUSTOM_SSL_CERT" -noout -ext subjectAltName 2>/dev/null | tr ',' '\n' | grep -oE 'DNS:[^ ]+' | sed 's/DNS://')"
    for d in $SERVER_NAMES; do
        [ "$d" = "_" ] && continue
        if ! grep -qx "$d" <<<"$CERT_NAMES"; then
            warn "O certificado não lista '$d' no campo Subject Alternative Name (SAN). Domínios encontrados no certificado: $(echo "$CERT_NAMES" | tr '\n' ' ')"
            warn "Isso faz o navegador mostrar aviso de segurança mesmo com um certificado válido — o domínio acessado precisa estar no SAN."
        fi
    done

    # ---- 3) Certificado expirado ou perto de vencer? ----
    if ! openssl x509 -in "$CUSTOM_SSL_CERT" -noout -checkend 0 >/dev/null 2>&1; then
        die "Este certificado já está EXPIRADO ($(openssl x509 -in "$CUSTOM_SSL_CERT" -noout -enddate | cut -d= -f2)). Peça a renovação na CA antes de continuar."
    fi
    if ! openssl x509 -in "$CUSTOM_SSL_CERT" -noout -checkend $((30 * 86400)) >/dev/null 2>&1; then
        warn "Este certificado vence em menos de 30 dias ($(openssl x509 -in "$CUSTOM_SSL_CERT" -noout -enddate | cut -d= -f2)). Não há renovação automática no modo 'custom' — programe-se para renovar na CA e rodar este script de novo."
    fi

    # ---- 4) Cadeia intermediária presente? (causa nº 1 do cadeado sumido) ----
    # Se CUSTOM_SSL_CHAIN não foi informado, tentamos aproveitar o próprio
    # CUSTOM_SSL_CERT — mas só ajuda de verdade se ele já for um "fullchain"
    # (certificado do domínio + intermediário(s) no mesmo arquivo).
    N_CERTS_IN_CERT_FILE="$(grep -c 'BEGIN CERTIFICATE' "$CUSTOM_SSL_CERT" || true)"
    if [ -z "$CUSTOM_SSL_CHAIN" ]; then
        if [ "$N_CERTS_IN_CERT_FILE" -ge 2 ]; then
            CUSTOM_SSL_CHAIN="$CUSTOM_SSL_CERT"
            info "CUSTOM_SSL_CHAIN não informado, mas $CUSTOM_SSL_CERT já contém $N_CERTS_IN_CERT_FILE certificados (parece um fullchain) — reaproveitando."
        else
            warn "CUSTOM_SSL_CHAIN não informado e $CUSTOM_SSL_CERT contém só 1 certificado (o do domínio, sem os intermediários da CA)."
            warn "ESTA É A CAUSA MAIS COMUM do 'x vermelho' / falta de cadeado com certificado já instalado: o navegador não consegue montar a cadeia de confiança até a CA raiz."
            warn "Baixe o(s) certificado(s) intermediário(s) no site da CA (ex.: DigiCert disponibiliza o 'CA Bundle' de download) e informe o caminho em configure-env.sh (CUSTOM_SSL_CHAIN), ou junte tudo em um único arquivo fullchain e aponte CUSTOM_SSL_CERT para ele."
            CUSTOM_SSL_CHAIN="$CUSTOM_SSL_CERT"
        fi
    elif [ ! -s "$CUSTOM_SSL_CHAIN" ]; then
        warn "CUSTOM_SSL_CHAIN aponta para '$CUSTOM_SSL_CHAIN', que não existe/está vazio — usando apenas o certificado do domínio (sem intermediários)."
        CUSTOM_SSL_CHAIN="$CUSTOM_SSL_CERT"
    else
        ok "Cadeia intermediária encontrada em $CUSTOM_SSL_CHAIN."
    fi

    # ---- 5) Copia os arquivos para um local gerenciado, com permissões corretas ----
    SSL_DIR_CUSTOM="/etc/nginx/ssl/midia-indoor-custom"
    mkdir -p "$SSL_DIR_CUSTOM"
    cp -f "$CUSTOM_SSL_CERT" "$SSL_DIR_CUSTOM/fullchain.pem"
    cp -f "$CUSTOM_SSL_KEY" "$SSL_DIR_CUSTOM/privkey.pem"
    cp -f "$CUSTOM_SSL_CHAIN" "$SSL_DIR_CUSTOM/chain.pem"
    chmod 600 "$SSL_DIR_CUSTOM/privkey.pem"
    chmod 644 "$SSL_DIR_CUSTOM/fullchain.pem" "$SSL_DIR_CUSTOM/chain.pem"

    TMP_CONF="$(mktemp)"
    sed \
        -e "s#__SERVER_NAMES__#${SERVER_NAMES}#g" \
        -e "s#__STATIC_PATH__#${STATIC_PATH}#g" \
        -e "s#__GUNICORN_BIND__#${GUNICORN_BIND}#g" \
        -e "s#__MAX_UPLOAD_MB__#${MAX_UPLOAD_MB}#g" \
        -e "s#__SSL_CERT__#${SSL_DIR_CUSTOM}/fullchain.pem#g" \
        -e "s#__SSL_KEY__#${SSL_DIR_CUSTOM}/privkey.pem#g" \
        -e "s#__SSL_CHAIN__#${SSL_DIR_CUSTOM}/chain.pem#g" \
        "$TEMPLATE_CUSTOM" >"$TMP_CONF"
    apply_http2_compat "$TMP_CONF"

    if safe_deploy_site "$TMP_CONF"; then
        ok "Nginx configurado e recarregado — HTTPS ativo com certificado comprado."
    else
        rm -f "$TMP_CONF"
        die "O Nginx recusou a configuração HTTPS com este certificado. Veja /tmp/nginx-test.log."
    fi
    rm -f "$TMP_CONF"

    PRIMARY_DOMAIN_CHECK="$(echo "$SERVER_NAMES" | awk '{print $1}')"
    if curl -fsSk --max-time 8 "https://$PRIMARY_DOMAIN_CHECK/healthz" >/dev/null 2>&1; then
        ok "Confirmado: https://$PRIMARY_DOMAIN_CHECK/healthz responde normalmente."
    else
        warn "https://$PRIMARY_DOMAIN_CHECK/healthz não respondeu no teste local — confira DNS/firewall/porta 443."
    fi
    info "Lembrete: este certificado NÃO renova sozinho. Quando a CA emitir a renovação, atualize os caminhos (se mudarem) e rode este script de novo, ou 'sudo deploy/scripts/check-https.sh' para acompanhar o vencimento."

elif [ "$SSL_MODE" = "letsencrypt" ]; then
    need_cmd certbot

    CERT_LIVE_DIR="/etc/letsencrypt/live/$PRIMARY_DOMAIN"
    CERT_FULLCHAIN="$CERT_LIVE_DIR/fullchain.pem"
    CERT_PRIVKEY="$CERT_LIVE_DIR/privkey.pem"
    CERT_CHAIN="$CERT_LIVE_DIR/chain.pem"

    HAVE_CERT=0
    [ -s "$CERT_FULLCHAIN" ] && [ -s "$CERT_PRIVKEY" ] && HAVE_CERT=1

    # ---- 1) Se ainda não há certificado, precisamos primeiro de um
    #         vhost HTTP simples (porta 80) para o desafio ACME funcionar ----
    if [ "$HAVE_CERT" = "0" ]; then
        title "Ainda não há certificado emitido — publicando vhost HTTP temporário para a validação"
        TMP_CONF="$(mktemp)"
        sed \
            -e "s#__SERVER_NAMES__#${SERVER_NAMES}#g" \
            -e "s#__STATIC_PATH__#${STATIC_PATH}#g" \
            -e "s#__GUNICORN_BIND__#${GUNICORN_BIND}#g" \
            -e "s#__MAX_UPLOAD_MB__#${MAX_UPLOAD_MB}#g" \
            "$TEMPLATE_HTTP" >"$TMP_CONF"
        if ! safe_deploy_site "$TMP_CONF"; then
            rm -f "$TMP_CONF"
            die "Não consegui publicar nem o vhost HTTP temporário. Veja /tmp/nginx-test.log."
        fi
        rm -f "$TMP_CONF"

        # ---- Confere se o(s) domínio(s) já resolvem para este servidor ----
        # Certbot falha (e pode até gerar bloqueio temporário por excesso de
        # tentativas) se o DNS ainda não propagou. Avisamos antes de tentar.
        title "Verificando DNS do(s) domínio(s)"
        PUBLIC_IP="$(detect_public_ip)"
        DNS_OK=1
        if [ -n "$PUBLIC_IP" ]; then
            info "IP público detectado deste servidor: $PUBLIC_IP"
            for d in $SERVER_NAMES; do
                RESOLVED_IPS="$(getent ahostsv4 "$d" 2>/dev/null | awk '{print $1}' | sort -u | tr '\n' ' ')"
                if [ -z "$RESOLVED_IPS" ]; then
                    warn "$d não resolveu para nenhum IP (DNS ainda não propagou?)."
                    DNS_OK=0
                elif ! grep -qw "$PUBLIC_IP" <<<"$RESOLVED_IPS"; then
                    warn "$d resolve para [$RESOLVED_IPS], mas este servidor é [$PUBLIC_IP] — confira o registro DNS tipo A."
                    DNS_OK=0
                else
                    ok "$d aponta corretamente para este servidor."
                fi
            done
        else
            warn "Não foi possível detectar o IP público deste servidor para conferir o DNS — seguindo mesmo assim."
        fi
        [ "$DNS_OK" = "0" ] && warn "Prosseguindo mesmo com possível problema de DNS (o Certbot fará a validação real a seguir)."

        # ---- Emite o certificado (sem deixar o certbot mexer no Nginx) ----
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

        if certbot certonly --webroot -w /var/www/certbot \
            --cert-name "$PRIMARY_DOMAIN" "${DOMAIN_ARGS[@]}" "${EMAIL_ARG[@]}" \
            --agree-tos --non-interactive; then
            ok "Certificado HTTPS emitido com sucesso."
            HAVE_CERT=1
        else
            warn "Falha ao emitir certificado. O site continua funcionando em HTTP por enquanto."
            warn "Verifique se o domínio já aponta (registro DNS tipo A) para o IP desta VPS e rode este script novamente:"
            warn "  sudo bash deploy/scripts/setup-nginx.sh $APP_DIR"
        fi
    else
        ok "Certificado já existe em $CERT_LIVE_DIR — reaproveitando (o Certbot cuida da renovação automática)."
    fi

    # ---- 2) Com o certificado em mãos, publica o vhost HTTPS definitivo ----
    if [ "$HAVE_CERT" = "1" ]; then
        title "Ativando HTTPS no Nginx"
        TMP_CONF="$(mktemp)"
        sed \
            -e "s#__SERVER_NAMES__#${SERVER_NAMES}#g" \
            -e "s#__STATIC_PATH__#${STATIC_PATH}#g" \
            -e "s#__GUNICORN_BIND__#${GUNICORN_BIND}#g" \
            -e "s#__MAX_UPLOAD_MB__#${MAX_UPLOAD_MB}#g" \
            -e "s#__SSL_CERT__#${CERT_FULLCHAIN}#g" \
            -e "s#__SSL_KEY__#${CERT_PRIVKEY}#g" \
            -e "s#__SSL_CHAIN__#${CERT_CHAIN}#g" \
            "$TEMPLATE_LETSENCRYPT" >"$TMP_CONF"
        apply_http2_compat "$TMP_CONF"

        if safe_deploy_site "$TMP_CONF"; then
            ok "Nginx configurado e recarregado — HTTPS ativo com certificado Let's Encrypt."
        else
            rm -f "$TMP_CONF"
            die "Certificado emitido, mas o Nginx recusou a configuração HTTPS. Veja /tmp/nginx-test.log e rode novamente."
        fi
        rm -f "$TMP_CONF"

        # ---- Garante o hook de recarregar o Nginx a cada renovação ----
        HOOK_DIR="/etc/letsencrypt/renewal-hooks/deploy"
        HOOK_FILE="$HOOK_DIR/reload-nginx-midia-indoor.sh"
        mkdir -p "$HOOK_DIR"
        cat >"$HOOK_FILE" <<'HOOK'
#!/usr/bin/env bash
# Instalado automaticamente por setup-nginx.sh do Nexo Mídia.
# Garante que o Nginx recarregue o certificado renovado.
nginx -t && systemctl reload nginx
HOOK
        chmod +x "$HOOK_FILE"

        # ---- Garante que a renovação automática está ativa ----
        if systemctl list-unit-files 2>/dev/null | grep -q '^certbot.timer'; then
            systemctl enable --now certbot.timer >/dev/null 2>&1
            if systemctl is-active --quiet certbot.timer; then
                ok "Renovação automática ativa (certbot.timer). Verifique quando roda: systemctl list-timers certbot.timer"
            else
                warn "certbot.timer existe mas não está ativo — renovação automática pode não funcionar. Rode: sudo systemctl enable --now certbot.timer"
            fi
        else
            warn "Timer certbot.timer não encontrado. A renovação automática pode depender de um cron próprio do pacote — confira com: sudo certbot renew --dry-run"
        fi

        # ---- Testa a renovação (não emite certificado novo, só simula) ----
        if certbot renew --cert-name "$PRIMARY_DOMAIN" --dry-run >/tmp/certbot-dry-run.log 2>&1; then
            ok "Teste de renovação automática (--dry-run) passou sem erros."
        else
            warn "Teste de renovação automática (--dry-run) falhou — veja /tmp/certbot-dry-run.log. O certificado atual continua válido; investigue antes do vencimento."
        fi

        # ---- Confirma que o site responde em HTTPS ----
        if curl -fsSk --max-time 8 "https://$PRIMARY_DOMAIN/healthz" >/dev/null 2>&1; then
            ok "Confirmado: https://$PRIMARY_DOMAIN/healthz responde normalmente."
        else
            warn "O certificado foi emitido, mas https://$PRIMARY_DOMAIN/healthz não respondeu no teste local."
            warn "Pode ser só o firewall/DNS ainda propagando — confira manualmente pelo navegador em alguns minutos."
        fi

        # ---- Confere se o Nginx está de fato servindo O MESMO certificado
        #      que está em disco (a causa mais comum do cadeado "sumir"
        #      mesmo com um certificado válido instalado) ----
        DISK_SERIAL="$(openssl x509 -in "$CERT_FULLCHAIN" -noout -serial 2>/dev/null | cut -d= -f2)"
        LIVE_SERIAL="$(echo | openssl s_client -servername "$PRIMARY_DOMAIN" -connect "127.0.0.1:443" 2>/dev/null | openssl x509 -noout -serial 2>/dev/null | cut -d= -f2)"
        if [ -n "$DISK_SERIAL" ] && [ -n "$LIVE_SERIAL" ]; then
            if [ "$DISK_SERIAL" = "$LIVE_SERIAL" ]; then
                ok "Confirmado: o Nginx está servindo exatamente o certificado emitido (nº de série $DISK_SERIAL)."
            else
                warn "O Nginx está respondendo com um certificado DIFERENTE do emitido (série $LIVE_SERIAL, esperado $DISK_SERIAL)."
                warn "Isso costuma indicar outro vhost/porta 443 conflitante, ou cache do navegador — rode check-https.sh para investigar."
            fi
        fi

        # ---- Verifica se há conteúdo misto (imagens/scripts em http://
        #      dentro de uma página https://) — o navegador mostra o
        #      cadeado com aviso ("não totalmente seguro") nesse caso ----
        MIXED="$(curl -fsSk --max-time 8 "https://$PRIMARY_DOMAIN/" 2>/dev/null | grep -oE 'src="http://[^"]+"|href="http://[^"]+"' | grep -v "$PRIMARY_DOMAIN" | head -5 || true)"
        if [ -n "$MIXED" ]; then
            warn "Encontrei referências a recursos em http:// (não https://) na página inicial:"
            echo "$MIXED" | sed 's/^/    /'
            warn "Isso causa o aviso de 'conteúdo não seguro'/cadeado quebrado no navegador mesmo com certificado válido."
            warn "Verifique URLs salvas no banco de dados (logo, imagens de capa, etc.) e troque para https:// ou caminhos relativos."
        fi
    fi
else
    TMP_CONF="$(mktemp)"
    sed \
        -e "s#__SERVER_NAMES__#${SERVER_NAMES}#g" \
        -e "s#__STATIC_PATH__#${STATIC_PATH}#g" \
        -e "s#__GUNICORN_BIND__#${GUNICORN_BIND}#g" \
        -e "s#__MAX_UPLOAD_MB__#${MAX_UPLOAD_MB}#g" \
        "$TEMPLATE_HTTP" >"$TMP_CONF"

    if safe_deploy_site "$TMP_CONF"; then
        ok "Nginx configurado e recarregado (HTTP)."
    else
        rm -f "$TMP_CONF"
        die "Não foi possível ativar o vhost HTTP. Veja /tmp/nginx-test.log."
    fi
    rm -f "$TMP_CONF"
fi

ok "Nginx pronto."
