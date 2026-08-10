#!/usr/bin/env bash
# =============================================================
# backup.sh — gera um pacote de backup completo do Nexo Mídia:
# banco de dados + .env + mídias enviadas (uploads) + metadados
# (commit git, domínio, data). Tudo num único .tar.gz autocontido,
# que pode ser guardado, baixado da VPS ou usado depois com
# restore.sh (mesma VPS) ou migrate.sh (VPS nova).
#
# Uso direto:
#   sudo bash deploy/scripts/backup.sh [APP_DIR] [tag]
#
# Normalmente você não precisa chamar isto diretamente — use o
# menu (sudo nexo -> "Backup") — mas funciona standalone também,
# inclusive para automatizar num cron.
#
# Uso interno (por restore.sh/migrate.sh, para capturar o caminho
# do arquivo gerado sem perder a saída na tela):
#   bash backup.sh "$APP_DIR" "$TAG" --result-file /tmp/algum-arquivo
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root

APP_DIR="${1:-/opt/midia-indoor}"
TAG="${2:-manual}"
RESULT_FILE=""
if [ "${3:-}" = "--result-file" ]; then
    RESULT_FILE="${4:?--result-file precisa de um caminho}"
fi

# Quantos backups completos manter (os mais antigos são apagados
# automaticamente depois de cada novo backup bem-sucedido). Pode
# ser mais alto que os "10 últimos" do backup rápido do update.sh
# porque este é o pacote completo, usado para restauração/migração.
KEEP="${NEXO_BACKUP_KEEP:-8}"

[ -f "$APP_DIR/wsgi.py" ] || die "Não encontrei wsgi.py em $APP_DIR — este não parece ser o diretório da instalação."
[ -f "$APP_DIR/.env" ] || die "$APP_DIR/.env não encontrado."

title "Backup completo — Nexo Mídia ($APP_DIR)"

set -a
# shellcheck disable=SC1091
source "$APP_DIR/.env"
set +a

TS="$(date -u +%Y%m%d-%H%M%S)"
SLUG="${SERVER_NAME:-sem-dominio}"
SLUG="$(printf '%s' "$SLUG" | tr -c 'a-zA-Z0-9._-' '-')"
PKG_NAME="backup-${SLUG}-${TAG}-${TS}"

BACKUP_ROOT="$APP_DIR/backups/full"
WORK_DIR="$(mktemp -d)"
STAGE_DIR="$WORK_DIR/$PKG_NAME"
mkdir -p "$STAGE_DIR" "$BACKUP_ROOT"

cleanup() { rm -rf "$WORK_DIR"; }
trap cleanup EXIT

# ---------------------------------------------------------------
# 1) Banco de dados
# ---------------------------------------------------------------
info "Copiando banco de dados..."
DB_KIND=""
if [[ "${DATABASE_URL:-}" == sqlite:///* ]]; then
    DB_KIND="sqlite"
    DB_PATH="${DATABASE_URL#sqlite:///}"
    [[ "$DB_PATH" = /* ]] || DB_PATH="$APP_DIR/$DB_PATH"
    if [ -f "$DB_PATH" ]; then
        cp "$DB_PATH" "$STAGE_DIR/database.sqlite3"
        ok "Banco SQLite copiado ($(du -h "$DB_PATH" | cut -f1))."
    else
        warn "DATABASE_URL aponta para SQLite mas o arquivo não existe ($DB_PATH) — pulando."
    fi
elif [[ "${DATABASE_URL:-}" == postgresql* ]]; then
    DB_KIND="postgresql"
    need_cmd pg_dump
    # --clean --if-exists --no-owner --no-privileges: gera um dump
    # que se restaura sozinho em cima de um banco vazio OU já
    # populado (dropa antes de recriar) e não depende do dump ter
    # sido feito com o mesmo usuário/dono de banco do destino — é
    # exatamente isso que permite restaurar num servidor novo, onde
    # o configure-env.sh gera um usuário/senha de Postgres diferentes.
    if pg_dump --clean --if-exists --no-owner --no-privileges \
        "${DATABASE_URL/postgresql+psycopg2/postgresql}" >"$STAGE_DIR/database.sql" 2>"$WORK_DIR/pg_dump.err"; then
        ok "Banco PostgreSQL exportado ($(du -h "$STAGE_DIR/database.sql" | cut -f1))."
    else
        cat "$WORK_DIR/pg_dump.err" >&2
        die "Falha ao exportar o PostgreSQL (pg_dump). Veja o erro acima."
    fi
else
    warn "DATABASE_URL não reconhecido ('${DATABASE_URL:-vazio}') — backup do banco pulado."
fi

# ---------------------------------------------------------------
# 2) .env (referência — restore.sh NÃO aplica isto automaticamente,
#    veja o aviso no manifesto e na documentação: cada servidor tem
#    suas próprias credenciais/segredos)
# ---------------------------------------------------------------
cp "$APP_DIR/.env" "$STAGE_DIR/env.snapshot"
chmod 600 "$STAGE_DIR/env.snapshot"

# ---------------------------------------------------------------
# 3) Mídias enviadas (uploads)
# ---------------------------------------------------------------
UPLOAD_DIR="$APP_DIR/${UPLOAD_FOLDER:-app/static/uploads}"
if [ -d "$UPLOAD_DIR" ] && [ -n "$(ls -A "$UPLOAD_DIR" 2>/dev/null)" ]; then
    info "Compactando mídias enviadas (uploads)..."
    tar -czf "$STAGE_DIR/uploads.tar.gz" -C "$(dirname "$UPLOAD_DIR")" "$(basename "$UPLOAD_DIR")"
    ok "Uploads compactados ($(du -h "$STAGE_DIR/uploads.tar.gz" | cut -f1))."
else
    info "Nenhuma mídia enviada encontrada em $UPLOAD_DIR — nada para compactar."
fi

# ---------------------------------------------------------------
# 4) Metadados (manifest.json) — usados por restore.sh/migrate.sh
#    para mostrar o que tem no pacote ANTES de aplicar, e para
#    detectar incompatibilidades óbvias (ex.: restaurar um dump
#    PostgreSQL num servidor configurado com SQLite).
# ---------------------------------------------------------------
GIT_COMMIT=""
GIT_BRANCH=""
if [ -d "$APP_DIR/.git" ]; then
    GIT_COMMIT="$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || true)"
    GIT_BRANCH="$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
fi

NEXO_MANIFEST_TAG="$TAG" \
NEXO_MANIFEST_DOMAIN="${SERVER_NAME:-}" \
NEXO_MANIFEST_DB_KIND="$DB_KIND" \
NEXO_MANIFEST_DB_NAME="${PG_DB_NAME:-}" \
NEXO_MANIFEST_GIT_COMMIT="$GIT_COMMIT" \
NEXO_MANIFEST_GIT_BRANCH="$GIT_BRANCH" \
NEXO_MANIFEST_APP_DIR="$APP_DIR" \
NEXO_MANIFEST_HAS_UPLOADS="$( [ -f "$STAGE_DIR/uploads.tar.gz" ] && echo 1 || echo 0 )" \
python3 - "$STAGE_DIR/manifest.json" <<'PYEOF'
import json, os, sys, socket, datetime

data = {
    "gerado_em_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "tag": os.environ.get("NEXO_MANIFEST_TAG", ""),
    "hostname": socket.gethostname(),
    "app_dir": os.environ.get("NEXO_MANIFEST_APP_DIR", ""),
    "dominio": os.environ.get("NEXO_MANIFEST_DOMAIN", ""),
    "banco": {
        "tipo": os.environ.get("NEXO_MANIFEST_DB_KIND", ""),
        "nome": os.environ.get("NEXO_MANIFEST_DB_NAME", ""),
    },
    "git_commit": os.environ.get("NEXO_MANIFEST_GIT_COMMIT", ""),
    "git_branch": os.environ.get("NEXO_MANIFEST_GIT_BRANCH", ""),
    "tem_uploads": os.environ.get("NEXO_MANIFEST_HAS_UPLOADS") == "1",
    "formato_versao": 1,
}
with open(sys.argv[1], "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
PYEOF

# ---------------------------------------------------------------
# 5) Empacotar tudo num único .tar.gz
# ---------------------------------------------------------------
FINAL_PKG="$BACKUP_ROOT/${PKG_NAME}.tar.gz"
tar -czf "$FINAL_PKG" -C "$WORK_DIR" "$PKG_NAME"
chmod 600 "$FINAL_PKG"
ok "Pacote de backup criado: $FINAL_PKG ($(du -h "$FINAL_PKG" | cut -f1))."

# ---------------------------------------------------------------
# 6) Poda de backups antigos (mantém os $KEEP mais recentes)
# ---------------------------------------------------------------
# shellcheck disable=SC2012
ls -1t "$BACKUP_ROOT"/backup-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    rm -f "$old"
    info "Backup antigo removido (mantendo os $KEEP mais recentes): $(basename "$old")"
done

if [ -n "$RESULT_FILE" ]; then
    printf '%s' "$FINAL_PKG" >"$RESULT_FILE"
fi

echo
info "Este pacote contém dados sensíveis (banco de dados completo e, em env.snapshot, segredos como SECRET_KEY e senha do banco) — guarde-o com o mesmo cuidado que um backup de senhas."
