#!/usr/bin/env bash
# =============================================================
# configure-env.sh — assistente interativo para gerar o .env
#
# Pode ser usado de duas formas:
#   1) Chamado automaticamente pelo install.sh durante a instalação.
#   2) Executado manualmente a qualquer momento para reconfigurar:
#        sudo deploy/scripts/configure-env.sh /opt/midia-indoor/.env
#
# Se nenhum caminho for informado, usa "./.env" (raiz do projeto),
# útil para configurar um ambiente de desenvolvimento local.
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

ENV_PATH="${1:-$SCRIPT_DIR/../../.env}"
ENV_PATH="$(python3 -c "import os,sys; print(os.path.abspath(sys.argv[1]))" "$ENV_PATH")"
title "Configuração do arquivo .env"
info "Arquivo de destino: $ENV_PATH"

# Carrega valores já existentes (para reaproveitar em reconfigurações)
declare -A CUR
if [ -f "$ENV_PATH" ]; then
    warn "Já existe um .env em $ENV_PATH — os valores atuais serão usados como padrão."
    while IFS='=' read -r k v; do
        [[ "$k" =~ ^[[:space:]]*# ]] && continue
        [ -z "$k" ] && continue
        CUR["$k"]="$v"
    done < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_PATH" || true)
fi

cur() { echo "${CUR[$1]:-$2}"; }

# ---------------------------------------------------------------
# 1) Domínio ou apenas IP da VPS
# ---------------------------------------------------------------
title "1/6 — Endereço público"
echo "Como os usuários vão acessar o sistema?"
ACCESS_MODE=""
choose "Modo de acesso" ACCESS_MODE "Tenho um domínio (ex: meusite.com.br)" "Vou usar apenas o IP da VPS (sem domínio por enquanto)"

if [[ "$ACCESS_MODE" == Tenho* ]]; then
    ask "Informe o domínio (sem http:// e sem www.)" "$(cur SERVER_NAME 'meusite.com.br')" DOMAIN
    if confirm "Deseja incluir também 'www.$DOMAIN'?" "s"; then
        SERVER_NAMES="$DOMAIN www.$DOMAIN"
    else
        SERVER_NAMES="$DOMAIN"
    fi
    HTTPS_CHOICE=""
    choose "Como ativar o HTTPS neste domínio?" HTTPS_CHOICE \
        "Let's Encrypt automático (gratuito, recomendado)" \
        "Já tenho/vou comprar um certificado de uma CA (DigiCert etc.) via CSR" \
        "Não ativar HTTPS agora"
    CUSTOM_SSL_CERT=""; CUSTOM_SSL_KEY=""; CUSTOM_SSL_CHAIN=""; LE_EMAIL=""
    case "$HTTPS_CHOICE" in
        "Let's Encrypt"*)
            SSL_MODE="letsencrypt"
            USE_HTTPS="1"
            ask "E-mail para avisos do certificado Let's Encrypt" "$(cur ADMIN_EMAIL 'admin@example.com')" LE_EMAIL
            ;;
        "Já tenho"*)
            SSL_MODE="custom"
            USE_HTTPS="1"
            echo
            info "Se ainda não gerou a chave/CSR para comprar o certificado, rode antes:"
            info "  sudo deploy/scripts/generate-csr.sh"
            info "e volte aqui depois de receber o certificado da CA."
            echo
            ask "Caminho do certificado (fullchain: seu certificado + intermediários da CA)" "$(cur CUSTOM_SSL_CERT '/etc/nginx/ssl/midia-indoor-csr/certificado.crt')" CUSTOM_SSL_CERT
            ask "Caminho da chave privada (a mesma usada para gerar o CSR)" "$(cur CUSTOM_SSL_KEY "/etc/nginx/ssl/midia-indoor-csr/${DOMAIN}.key")" CUSTOM_SSL_KEY
            ask "Caminho do(s) certificado(s) intermediário(s)/CA bundle (deixe em branco se já estiver junto no fullchain acima)" "$(cur CUSTOM_SSL_CHAIN '')" CUSTOM_SSL_CHAIN
            warn "Não encontrando os intermediários da CA agora? O setup-nginx.sh detecta isso e avisa — é a causa nº 1 do navegador não mostrar o cadeado mesmo com certificado instalado."
            ;;
        *)
            SSL_MODE="none"
            USE_HTTPS="0"
            ;;
    esac
    SERVER_NAME_PRIMARY="$DOMAIN"
else
    DETECTED_IP="$(detect_public_ip)"
    ask "IP público (da VPS, ou o IP de onde estiver rodando)" "$(cur SERVER_NAME "$DETECTED_IP")" SERVER_NAME_PRIMARY
    SERVER_NAMES="$SERVER_NAME_PRIMARY"
    LE_EMAIL=""
    CUSTOM_SSL_CERT=""; CUSTOM_SSL_KEY=""; CUSTOM_SSL_CHAIN=""
    warn "Sem domínio não é possível emitir certificado HTTPS confiável (Let's Encrypt exige um domínio)."
    if confirm "Ativar HTTPS mesmo assim, com um certificado autoassinado (a conexão fica criptografada, mas o navegador mostra um aviso de segurança na primeira visita — normal sem domínio)?" "s"; then
        SSL_MODE="selfsigned"
        USE_HTTPS="1"
        ok "HTTPS com certificado autoassinado será gerado por 'setup-nginx.sh' (openssl, local, sem depender de nenhum serviço externo)."
        info "Quando tiver um domínio, rode este assistente de novo e escolha 'Tenho um domínio' + Let's Encrypt para trocar pelo certificado confiável."
    else
        SSL_MODE="none"
        USE_HTTPS="0"
        warn "O site funcionará apenas em HTTP."
    fi
fi

# ---------------------------------------------------------------
# 2) Segredos
# ---------------------------------------------------------------
title "2/6 — Chaves de segurança"
EXISTING_SECRET="$(cur SECRET_KEY '')"
if [ -n "$EXISTING_SECRET" ] && [ "$EXISTING_SECRET" != "troque-esta-chave-em-producao-0000000000000000000000000000" ]; then
    if confirm "Já existe uma SECRET_KEY configurada. Manter a mesma?" "s"; then
        SECRET_KEY="$EXISTING_SECRET"
    else
        SECRET_KEY="$(gen_secret)"
    fi
else
    SECRET_KEY="$(gen_secret)"
    ok "SECRET_KEY gerada automaticamente."
fi
SECURITY_PASSWORD_SALT="$(cur SECURITY_PASSWORD_SALT '')"
if [ -z "$SECURITY_PASSWORD_SALT" ] || [ "$SECURITY_PASSWORD_SALT" = "troque-este-salt-0000000000000000000000000000000" ]; then
    SECURITY_PASSWORD_SALT="$(gen_secret)"
fi

# ---------------------------------------------------------------
# 3) Banco de dados
# ---------------------------------------------------------------
title "3/6 — Banco de dados"
DB_CHOICE=""
choose "Qual banco de dados usar?" DB_CHOICE \
    "PostgreSQL (recomendado em produção)" \
    "SQLite (mais simples, ideal para testes ou VPS pequena)"

if [[ "$DB_CHOICE" == PostgreSQL* ]]; then
    ask "Nome do banco" "$(cur PG_DB_NAME 'nexo_midia')" PG_DB_NAME
    ask "Usuário do banco" "$(cur PG_DB_USER 'nexo_user')" PG_DB_USER
    # Normaliza para minúsculas: identificadores do Postgres sem aspas são
    # dobrados para minúsculo automaticamente na criação, então nomes com
    # maiúscula ("Digital_promo") causavam "database ... does not exist"
    # ao conectar (o real era "digital_promo"). Evitamos a pegadinha toda
    # já usando minúsculas em todo lugar.
    PG_DB_NAME="$(echo "$PG_DB_NAME" | tr '[:upper:]' '[:lower:]')"
    PG_DB_USER="$(echo "$PG_DB_USER" | tr '[:upper:]' '[:lower:]')"
    EXISTING_PG_PW="$(cur PG_DB_PASSWORD '')"
    if [ -n "$EXISTING_PG_PW" ] && confirm "Manter a senha do banco já configurada?" "s"; then
        PG_DB_PASSWORD="$EXISTING_PG_PW"
    else
        PG_DB_PASSWORD="$(gen_secret | cut -c1-24)"
        ok "Senha do banco gerada automaticamente (também salva no .env)."
    fi
    DATABASE_URL="postgresql+psycopg2://${PG_DB_USER}:${PG_DB_PASSWORD}@localhost:5432/${PG_DB_NAME}"

    if command -v psql >/dev/null 2>&1 && [ "$(id -u)" -eq 0 ]; then
        if confirm "Criar/atualizar automaticamente o usuário e o banco no PostgreSQL agora?" "s"; then
            sudo -u postgres psql -v ON_ERROR_STOP=1 <<-SQL
                DO \$\$
                BEGIN
                   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${PG_DB_USER}') THEN
                      CREATE ROLE "${PG_DB_USER}" LOGIN PASSWORD '${PG_DB_PASSWORD}';
                   ELSE
                      ALTER ROLE "${PG_DB_USER}" WITH PASSWORD '${PG_DB_PASSWORD}';
                   END IF;
                END
                \$\$;
                SELECT 'CREATE DATABASE "${PG_DB_NAME}" OWNER "${PG_DB_USER}"'
                WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${PG_DB_NAME}')\gexec
SQL
            ok "Banco '${PG_DB_NAME}' e usuário '${PG_DB_USER}' prontos."
        fi
    fi
else
    DATABASE_URL="$(cur DATABASE_URL 'sqlite:///instance/prod.sqlite3')"
    PG_DB_NAME=""; PG_DB_USER=""; PG_DB_PASSWORD=""
fi

# ---------------------------------------------------------------
# 4) Rate limiting (Redis)
# ---------------------------------------------------------------
title "4/6 — Limitação de requisições (rate limiting)"
if confirm "Usar Redis para rate limiting entre múltiplos workers (recomendado em produção)?" "s"; then
    RATELIMIT_STORAGE_URI="redis://localhost:6379/0"
    USE_REDIS="1"
else
    RATELIMIT_STORAGE_URI="memory://"
    USE_REDIS="0"
    warn "Sem Redis, os limites de requisição não são compartilhados entre workers do Gunicorn."
fi

# ---------------------------------------------------------------
# 5) Dados da empresa
# ---------------------------------------------------------------
title "5/6 — Dados exibidos no site"
ask "Nome da empresa" "$(cur COMPANY_NAME 'Nexo Mídia')" COMPANY_NAME
ask "WhatsApp (somente números, com DDI+DDD)" "$(cur COMPANY_WHATSAPP '5567999990000')" COMPANY_WHATSAPP
ask "E-mail de contato" "$(cur COMPANY_EMAIL 'contato@example.com')" COMPANY_EMAIL
ask "Telefone (exibição)" "$(cur COMPANY_PHONE '(00) 0000-0000')" COMPANY_PHONE
ask "Endereço (exibição)" "$(cur COMPANY_ADDRESS 'Sua cidade, UF')" COMPANY_ADDRESS

# ---------------------------------------------------------------
# 6) Administrador inicial
# ---------------------------------------------------------------
title "6/6 — Usuário administrador"
ask "Nome do administrador" "$(cur ADMIN_NAME 'Administrador Principal')" ADMIN_NAME
ask "E-mail do administrador (login)" "$(cur ADMIN_EMAIL 'admin@example.com')" ADMIN_EMAIL
if confirm "Gerar uma senha forte automaticamente para o administrador?" "s"; then
    ADMIN_PASSWORD="$(gen_secret | cut -c1-16)"
    ok "Senha gerada: ${C_BOLD}${ADMIN_PASSWORD}${C_RESET}  (anote agora — ela também fica salva no .env)"
else
    ask_secret "Senha do administrador" ADMIN_PASSWORD
fi

# ---------------------------------------------------------------
# Grava o .env
# ---------------------------------------------------------------
mkdir -p "$(dirname "$ENV_PATH")"
umask 077
cat >"$ENV_PATH" <<ENVEOF
# ============================================================
# NEXO MÍDIA — .env gerado por deploy/scripts/configure-env.sh
# Gerado em: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# NÃO versione este arquivo.
# ============================================================

FLASK_ENV=production
FLASK_APP=wsgi.py
FLASK_DEBUG=0

# ---- Endereço público ----
SERVER_NAME="${SERVER_NAME_PRIMARY}"
SERVER_NAMES="${SERVER_NAMES}"
USE_HTTPS=${USE_HTTPS}
# SSL_MODE: letsencrypt (domínio) | selfsigned (acesso por IP) | custom (certificado comprado via CSR) | none (HTTP)
SSL_MODE="${SSL_MODE}"
LETSENCRYPT_EMAIL="${LE_EMAIL}"
# ---- Certificado comprado via CSR (só usado quando SSL_MODE=custom) ----
CUSTOM_SSL_CERT="${CUSTOM_SSL_CERT}"
CUSTOM_SSL_KEY="${CUSTOM_SSL_KEY}"
CUSTOM_SSL_CHAIN="${CUSTOM_SSL_CHAIN}"

# ---- Segurança ----
SECRET_KEY="${SECRET_KEY}"
SECURITY_PASSWORD_SALT="${SECURITY_PASSWORD_SALT}"

# ---- Banco de dados ----
DATABASE_URL="${DATABASE_URL}"
SQLALCHEMY_POOL_SIZE=10
SQLALCHEMY_MAX_OVERFLOW=20
SQLALCHEMY_POOL_RECYCLE=1800
SQLALCHEMY_POOL_PRE_PING=1
PG_DB_NAME="${PG_DB_NAME}"
PG_DB_USER="${PG_DB_USER}"
PG_DB_PASSWORD="${PG_DB_PASSWORD}"

# ---- Sessão / Cookies ----
SESSION_COOKIE_SECURE=${USE_HTTPS}
REMEMBER_COOKIE_SECURE=${USE_HTTPS}
PERMANENT_SESSION_LIFETIME_MINUTES=60

# ---- Rate Limiting ----
RATELIMIT_STORAGE_URI="${RATELIMIT_STORAGE_URI}"
RATELIMIT_DEFAULT="200 per day;50 per hour"

# ---- Uploads ----
UPLOAD_FOLDER=app/static/uploads
MAX_CONTENT_LENGTH_MB=80
ALLOWED_IMAGE_EXTENSIONS=jpg,jpeg,png,webp,gif
ALLOWED_VIDEO_EXTENSIONS=mp4,webm

# ---- WhatsApp / Empresa ----
COMPANY_NAME="${COMPANY_NAME}"
COMPANY_WHATSAPP="${COMPANY_WHATSAPP}"
COMPANY_EMAIL="${COMPANY_EMAIL}"
COMPANY_PHONE="${COMPANY_PHONE}"
COMPANY_ADDRESS="${COMPANY_ADDRESS}"

# ---- Administrador inicial (usado por "flask create-admin") ----
ADMIN_NAME="${ADMIN_NAME}"
ADMIN_EMAIL="${ADMIN_EMAIL}"
ADMIN_PASSWORD="${ADMIN_PASSWORD}"

# ---- Logs ----
LOG_LEVEL=INFO
LOG_DIR=logs
LOG_TO_STDOUT=1

# ---- CORS ----
CORS_ORIGINS=

# ---- Proxy reverso (Nginx sempre na frente neste deploy) ----
BEHIND_PROXY=1

# ---- HTTPS / Talisman ----
FORCE_HTTPS=${USE_HTTPS}

# ---- Gunicorn ----
GUNICORN_BIND=127.0.0.1:8000
GUNICORN_WORKERS=
GUNICORN_THREADS=2
GUNICORN_TIMEOUT=30
GUNICORN_LOG_LEVEL=info
ENVEOF

chmod 600 "$ENV_PATH"
ok ".env gravado em $ENV_PATH"

if [ "$USE_REDIS" = "1" ]; then
    export NEXO_NEEDS_REDIS=1
fi
export NEXO_USE_HTTPS="$USE_HTTPS"
export NEXO_SSL_MODE="$SSL_MODE"
export NEXO_SERVER_NAME="$SERVER_NAME_PRIMARY"
export NEXO_SERVER_NAMES="$SERVER_NAMES"
export NEXO_LE_EMAIL="$LE_EMAIL"
export NEXO_ACCESS_MODE="$ACCESS_MODE"
