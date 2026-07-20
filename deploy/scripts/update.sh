#!/usr/bin/env bash
# =============================================================
# update.sh — publica uma nova versão do Nexo Mídia com segurança:
#   1. faz backup do banco de dados e do .env
#   2. publica o novo código numa release separada (não mexe na
#      que está no ar até tudo estar pronto)
#   3. instala dependências e roda as migrações do banco
#   4. troca o symlink "current" de forma atômica
#   5. reinicia o serviço e verifica o /healthz
#   6. se algo falhar, desfaz tudo automaticamente (rollback)
#
# Uso:
#   1) Envie a nova versão do código para a VPS (git pull, scp, etc.)
#   2) Rode, de dentro da pasta com o novo código:
#        sudo bash deploy/scripts/update.sh
#
#   Parâmetros opcionais:
#        sudo bash deploy/scripts/update.sh [APP_DIR] [SOURCE_DIR]
#
#   Para automação (CI/cron), pule as confirmações com:
#        sudo AUTO_YES=1 bash deploy/scripts/update.sh
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root

APP_DIR="${1:-/opt/midia-indoor}"
SOURCE_DIR="${2:-$(pwd)}"
AUTO_YES="${AUTO_YES:-0}"
KEEP_RELEASES=5
APP_USER="midia-indoor"
APP_GROUP="midia-indoor"

[ -f "$SOURCE_DIR/wsgi.py" ] || die "Não encontrei wsgi.py em $SOURCE_DIR. Rode este script de dentro da pasta com o novo código, ou informe o caminho: update.sh $APP_DIR /caminho/do/codigo"
[ -L "$APP_DIR/current" ] || die "$APP_DIR não parece ter sido instalado com install.sh (current ausente)."
[ -f "$APP_DIR/shared/.env" ] || die "$APP_DIR/shared/.env não encontrado."

maybe_confirm() {
    [ "$AUTO_YES" = "1" ] && return 0
    confirm "$1" "${2:-s}"
}

PREV_RELEASE="$(readlink -f "$APP_DIR/current")"
title "Atualização segura — Nexo Mídia"
info "Release atual: $(basename "$PREV_RELEASE")"
info "Novo código:   $SOURCE_DIR"

# ---------------------------------------------------------------
# 1) Backup
# ---------------------------------------------------------------
title "1/6 — Backup do banco de dados e do .env"
TS="$(date -u +%Y%m%d%H%M%S)"
BACKUP_DIR="$APP_DIR/shared/backups"
mkdir -p "$BACKUP_DIR"
cp "$APP_DIR/shared/.env" "$BACKUP_DIR/env-$TS.bak"

set -a
# shellcheck disable=SC1091
source "$APP_DIR/shared/.env"
set +a

if [[ "${DATABASE_URL:-}" == sqlite:///* ]]; then
    DB_PATH="${DATABASE_URL#sqlite:///}"
    [[ "$DB_PATH" = /* ]] || DB_PATH="$APP_DIR/current/$DB_PATH"
    if [ -f "$DB_PATH" ]; then
        cp "$DB_PATH" "$BACKUP_DIR/db-$TS.sqlite3"
        ok "Backup do SQLite salvo em $BACKUP_DIR/db-$TS.sqlite3"
    fi
elif [[ "${DATABASE_URL:-}" == postgresql* ]]; then
    PG_URI="${DATABASE_URL/postgresql+psycopg2/postgresql}"
    if command -v pg_dump >/dev/null 2>&1; then
        if pg_dump "$PG_URI" >"$BACKUP_DIR/db-$TS.sql" 2>/dev/null; then
            ok "Backup do PostgreSQL salvo em $BACKUP_DIR/db-$TS.sql"
        else
            warn "Não foi possível gerar o backup automático do PostgreSQL. Prosseguindo mesmo assim."
        fi
    fi
fi
# Mantém apenas os 10 backups mais recentes de cada tipo
ls -1t "$BACKUP_DIR"/db-* 2>/dev/null | tail -n +11 | xargs -r rm -f
ls -1t "$BACKUP_DIR"/env-* 2>/dev/null | tail -n +11 | xargs -r rm -f

# ---------------------------------------------------------------
# 2) Publicar novo código em release separada
# ---------------------------------------------------------------
title "2/6 — Publicando novo código"
RELEASE_DIR="$APP_DIR/releases/$TS"
mkdir -p "$RELEASE_DIR"
rsync -a \
    --exclude ".git" --exclude ".github" \
    --exclude "__pycache__" --exclude "*.pyc" \
    --exclude "node_modules" --exclude ".env" \
    --exclude "instance" --exclude "logs" \
    --exclude "app/static/uploads" \
    "$SOURCE_DIR/" "$RELEASE_DIR/"

rm -rf "$RELEASE_DIR/app/static/uploads"
ln -sfn "$APP_DIR/shared/uploads" "$RELEASE_DIR/app/static/uploads"
rm -rf "$RELEASE_DIR/logs"
ln -sfn "$APP_DIR/shared/logs" "$RELEASE_DIR/logs"
rm -rf "$RELEASE_DIR/instance"
ln -sfn "$APP_DIR/shared/instance" "$RELEASE_DIR/instance"
ok "Nova release publicada em $RELEASE_DIR (a versão em produção ainda não foi trocada)."

# ---------------------------------------------------------------
# 3) Dependências
# ---------------------------------------------------------------
title "3/6 — Instalando dependências"
"$APP_DIR/shared/venv/bin/pip" install --upgrade pip wheel >/dev/null
"$APP_DIR/shared/venv/bin/pip" install -r "$RELEASE_DIR/requirements.txt"
ok "Dependências Python atualizadas."

if [ -f "$RELEASE_DIR/package.json" ] && command -v npm >/dev/null 2>&1; then
    if maybe_confirm "Reconstruir os assets de front-end (Tailwind CSS)?" "s"; then
        (cd "$RELEASE_DIR" && npm ci && npm run build)
        ok "Assets de front-end reconstruídos."
    fi
fi

# ---------------------------------------------------------------
# 4) Migrações do banco
# ---------------------------------------------------------------
title "4/6 — Aplicando migrações do banco de dados"
export FLASK_APP=wsgi.py
if ! (cd "$RELEASE_DIR" && "$APP_DIR/shared/venv/bin/flask" db upgrade); then
    err "Falha ao aplicar as migrações. A versão em produção NÃO foi alterada."
    err "Corrija o problema e rode o update.sh novamente. Backup do banco está em $BACKUP_DIR."
    exit 1
fi
ok "Migrações aplicadas com sucesso."

chown -R "$APP_USER:$APP_GROUP" "$RELEASE_DIR"

# ---------------------------------------------------------------
# 5) Troca atômica da versão em produção
# ---------------------------------------------------------------
title "5/6 — Ativando a nova versão"
ln -sfn "$RELEASE_DIR" "$APP_DIR/current"
systemctl restart midia-indoor

BIND="$(grep -E '^GUNICORN_BIND=' "$APP_DIR/shared/.env" | cut -d= -f2- || true)"
BIND="${BIND:-127.0.0.1:8000}"

HEALTHY=0
for i in $(seq 1 15); do
    sleep 1
    if curl -fsS "http://$BIND/healthz" >/dev/null 2>&1; then
        HEALTHY=1
        break
    fi
done

if [ "$HEALTHY" = "1" ]; then
    ok "Nova versão no ar e respondendo em /healthz."
else
    err "A nova versão não respondeu corretamente ao /healthz. Revertendo (rollback automático)..."
    ln -sfn "$PREV_RELEASE" "$APP_DIR/current"
    systemctl restart midia-indoor
    err "Rollback concluído — a versão anterior ($(basename "$PREV_RELEASE")) está novamente ativa."
    err "Verifique os logs da nova release antes de tentar de novo: sudo journalctl -u midia-indoor -n 100"
    exit 1
fi

# ---------------------------------------------------------------
# 6) Limpeza de releases antigas
# ---------------------------------------------------------------
title "6/6 — Limpando releases antigas"
ls -1dt "$APP_DIR"/releases/*/ 2>/dev/null | tail -n +$((KEEP_RELEASES + 1)) | while read -r old; do
    info "Removendo release antiga: $(basename "$old")"
    rm -rf "$old"
done

echo
ok "Atualização concluída com sucesso. Release ativa: $TS"
echo "   Para reverter manualmente a qualquer momento: sudo bash deploy/scripts/rollback.sh"
