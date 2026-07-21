#!/usr/bin/env bash
# =============================================================
# update.sh — publica uma atualização do Nexo Mídia.
#
# Modo git (recomendado — instalado com histórico git):
#   cd /opt/midia-indoor && sudo bash deploy/scripts/update.sh
#   -> faz "git pull" e segue o resto do processo.
#
# Modo zip (sem git): envie o novo código para a VPS e rode, de
# dentro da pasta extraída:
#   sudo bash deploy/scripts/update.sh /opt/midia-indoor
#   -> copia (rsync) o código novo por cima do que está em produção,
#      preservando venv/.env/uploads/logs/instance.
#
# Em qualquer um dos dois modos, o script:
#   1. faz backup rápido do banco e do .env
#   2. instala dependências novas/atualizadas
#   3. roda as migrações do banco (se falhar, para aqui sem tocar
#      em mais nada)
#   4. reinicia o serviço e confere /healthz
#   5. se /healthz não responder e o deploy for via git, desfaz o
#      "git pull" automaticamente (git reset --hard) e reinicia
#      com a versão anterior
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root

APP_DIR="${1:-/opt/midia-indoor}"
[ -f "$APP_DIR/wsgi.py" ] || die "Não encontrei wsgi.py em $APP_DIR."
[ -f "$APP_DIR/.env" ] || die "$APP_DIR/.env não encontrado."

title "Atualização — Nexo Mídia ($APP_DIR)"

# ---------------------------------------------------------------
# 1) Backup rápido (banco + .env)
# ---------------------------------------------------------------
title "1/4 — Backup"
TS="$(date -u +%Y%m%d%H%M%S)"
BACKUP_DIR="$APP_DIR/backups"
mkdir -p "$BACKUP_DIR"
cp "$APP_DIR/.env" "$BACKUP_DIR/env-$TS.bak"

set -a
# shellcheck disable=SC1091
source "$APP_DIR/.env"
set +a

if [[ "${DATABASE_URL:-}" == sqlite:///* ]]; then
    DB_PATH="${DATABASE_URL#sqlite:///}"
    [[ "$DB_PATH" = /* ]] || DB_PATH="$APP_DIR/$DB_PATH"
    [ -f "$DB_PATH" ] && cp "$DB_PATH" "$BACKUP_DIR/db-$TS.sqlite3" && ok "Backup do SQLite salvo."
elif [[ "${DATABASE_URL:-}" == postgresql* ]] && command -v pg_dump >/dev/null 2>&1; then
    pg_dump "${DATABASE_URL/postgresql+psycopg2/postgresql}" >"$BACKUP_DIR/db-$TS.sql" 2>/dev/null \
        && ok "Backup do PostgreSQL salvo." \
        || warn "Não foi possível gerar o backup automático do PostgreSQL. Prosseguindo mesmo assim."
fi
ls -1t "$BACKUP_DIR"/db-* 2>/dev/null | tail -n +11 | xargs -r rm -f
ls -1t "$BACKUP_DIR"/env-* 2>/dev/null | tail -n +11 | xargs -r rm -f

# ---------------------------------------------------------------
# 2) Publicar o código novo
# ---------------------------------------------------------------
title "2/4 — Publicando o código novo"
PREV_COMMIT=""
if [ -d "$APP_DIR/.git" ]; then
    PREV_COMMIT="$(git -C "$APP_DIR" rev-parse HEAD)"
    git -C "$APP_DIR" pull --ff-only
    ok "git pull concluído (era $PREV_COMMIT)."
else
    SOURCE_DIR="$(pwd)"
    [ -f "$SOURCE_DIR/wsgi.py" ] || die "Rode este comando de dentro da pasta com o código novo, ex.: cd ~/midia-indoor-novo && sudo bash $APP_DIR/deploy/scripts/update.sh $APP_DIR"
    rsync -a \
        --exclude ".git" --exclude "__pycache__" --exclude "*.pyc" \
        --exclude "node_modules" --exclude ".env" \
        --exclude "instance" --exclude "logs" --exclude "venv" \
        --exclude "app/static/uploads" --exclude "backups" \
        "$SOURCE_DIR/" "$APP_DIR/"
    ok "Código copiado por cima de $APP_DIR (rsync)."
fi

# ---------------------------------------------------------------
# 3) Dependências + migrações
# ---------------------------------------------------------------
title "3/4 — Dependências e migrações"
"$APP_DIR/venv/bin/pip" install --upgrade pip wheel >/dev/null
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
ok "Dependências Python atualizadas."

if [ -f "$APP_DIR/package.json" ] && command -v npm >/dev/null 2>&1; then
    (cd "$APP_DIR" && npm ci && npm run build) && ok "Assets de front-end reconstruídos."
fi

export FLASK_APP=wsgi.py
if ! (cd "$APP_DIR" && "$APP_DIR/venv/bin/flask" db upgrade); then
    err "Falha ao aplicar as migrações. O serviço NÃO foi reiniciado."
    err "Corrija o problema e rode o update.sh novamente. Backup do banco está em $BACKUP_DIR."
    exit 1
fi
ok "Migrações aplicadas."
chown -R midia-indoor:midia-indoor "$APP_DIR"

# ---------------------------------------------------------------
# 4) Reiniciar e checar /healthz
# ---------------------------------------------------------------
title "4/4 — Reiniciando e verificando"
systemctl restart midia-indoor

BIND="$(grep -E '^GUNICORN_BIND=' "$APP_DIR/.env" | cut -d= -f2- || true)"
BIND="${BIND:-127.0.0.1:8000}"

HEALTHY=0
for i in $(seq 1 15); do
    sleep 1
    curl -fsS "http://$BIND/healthz" >/dev/null 2>&1 && { HEALTHY=1; break; }
done

if [ "$HEALTHY" = "1" ]; then
    ok "Atualização concluída — nova versão no ar e respondendo em /healthz."
    exit 0
fi

err "A nova versão não respondeu em /healthz."
if [ -n "$PREV_COMMIT" ]; then
    err "Revertendo automaticamente (git reset --hard $PREV_COMMIT)..."
    git -C "$APP_DIR" reset --hard "$PREV_COMMIT"
    "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" >/dev/null
    (cd "$APP_DIR" && "$APP_DIR/venv/bin/flask" db upgrade) || true
    systemctl restart midia-indoor
    err "Rollback concluído — versão anterior ($PREV_COMMIT) ativa novamente."
else
    err "Deploy via zip/rsync não tem rollback automático. Restaure o backup se necessário: $BACKUP_DIR"
fi
err "Verifique os logs antes de tentar de novo: sudo journalctl -u midia-indoor -n 100"
exit 1
