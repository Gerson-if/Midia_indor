#!/usr/bin/env bash
# =============================================================
# restore.sh — restaura um pacote gerado por backup.sh: banco de
# dados + mídias enviadas (uploads). O .env do pacote é mostrado
# só como referência (env.snapshot dentro do pacote extraído) —
# NUNCA é aplicado automaticamente, porque cada servidor tem suas
# próprias credenciais (SECRET_KEY, senha do Postgres, domínio).
# Se precisar reaproveitar algo de lá, copie manualmente o que
# fizer sentido.
#
# Uso:
#   sudo bash deploy/scripts/restore.sh [APP_DIR]
#   sudo bash deploy/scripts/restore.sh [APP_DIR] /caminho/para/backup-....tar.gz
#
# Sem o segundo argumento, lista os backups disponíveis em
# <APP_DIR>/backups/full e deixa você escolher.
#
# Segurança: antes de sobrescrever qualquer coisa, este script
# SEMPRE cria automaticamente um backup do estado atual (tag
# "pre-restore"), então mesmo uma restauração por engano pode ser
# desfeita restaurando esse backup de segurança logo em seguida.
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root
need_cmd python3

APP_DIR="${1:-/opt/midia-indoor}"
PKG_PATH="${2:-}"

[ -f "$APP_DIR/wsgi.py" ] || die "Não encontrei wsgi.py em $APP_DIR."
[ -f "$APP_DIR/.env" ] || die "$APP_DIR/.env não encontrado."

title "Restaurar backup — Nexo Mídia ($APP_DIR)"

BACKUP_ROOT="$APP_DIR/backups/full"

if [ -z "$PKG_PATH" ]; then
    mapfile -t PACKAGES < <(ls -1t "$BACKUP_ROOT"/backup-*.tar.gz 2>/dev/null || true)
    [ "${#PACKAGES[@]}" -gt 0 ] || die "Nenhum backup encontrado em $BACKUP_ROOT. Gere um com: sudo bash deploy/scripts/backup.sh $APP_DIR"
    echo -e "${C_BOLD}?${C_RESET} Backups disponíveis (mais recente primeiro):"
    i=1
    for p in "${PACKAGES[@]}"; do
        SZ="$(du -h "$p" | cut -f1)"
        DT="$(date -r "$p" '+%d/%m/%Y %H:%M')"
        echo "   $i) $(basename "$p")  (${SZ}, ${DT})"
        i=$((i + 1))
    done
    read -r -p "   Escolha [1-${#PACKAGES[@]}]: " CHOICE
    if [[ "$CHOICE" =~ ^[0-9]+$ ]] && [ "$CHOICE" -ge 1 ] && [ "$CHOICE" -le "${#PACKAGES[@]}" ]; then
        PKG_PATH="${PACKAGES[$((CHOICE - 1))]}"
    else
        die "Opção inválida."
    fi
fi

[ -f "$PKG_PATH" ] || die "Pacote não encontrado: $PKG_PATH"

# ---------------------------------------------------------------
# 1) Extrair e mostrar o manifesto ANTES de mexer em qualquer coisa
# ---------------------------------------------------------------
WORK_DIR="$(mktemp -d)"
cleanup() { rm -rf "$WORK_DIR"; }
trap cleanup EXIT

tar -xzf "$PKG_PATH" -C "$WORK_DIR"
EXTRACTED_DIR="$(find "$WORK_DIR" -mindepth 1 -maxdepth 1 -type d | head -1)"
[ -n "$EXTRACTED_DIR" ] || die "Pacote inválido — não encontrei a pasta esperada dentro do .tar.gz."
[ -f "$EXTRACTED_DIR/manifest.json" ] || die "Pacote inválido — manifest.json ausente."

title "1/5 — Conteúdo do pacote"
python3 - "$EXTRACTED_DIR/manifest.json" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    m = json.load(f)
print(f"  Gerado em:   {m.get('gerado_em_utc', '?')} UTC (tag: {m.get('tag', '?')})")
print(f"  Servidor:    {m.get('hostname', '?')}  (dir: {m.get('app_dir', '?')})")
print(f"  Domínio:     {m.get('dominio') or '(sem domínio configurado)'}")
banco = m.get('banco', {})
print(f"  Banco:       {banco.get('tipo', '?')}  {banco.get('nome', '')}")
print(f"  Git commit:  {m.get('git_commit') or '(sem git)'} ({m.get('git_branch', '')})")
print(f"  Uploads:     {'sim' if m.get('tem_uploads') else 'não'}")
PYEOF

HAS_DB_SQLITE=0; HAS_DB_PG=0
[ -f "$EXTRACTED_DIR/database.sqlite3" ] && HAS_DB_SQLITE=1
[ -f "$EXTRACTED_DIR/database.sql" ] && HAS_DB_PG=1

set -a
# shellcheck disable=SC1091
source "$APP_DIR/.env"
set +a
CURRENT_DB_KIND="desconhecido"
[[ "${DATABASE_URL:-}" == sqlite:///* ]] && CURRENT_DB_KIND="sqlite"
[[ "${DATABASE_URL:-}" == postgresql* ]] && CURRENT_DB_KIND="postgresql"

if [ "$HAS_DB_PG" = "1" ] && [ "$CURRENT_DB_KIND" != "postgresql" ]; then
    warn "O pacote tem um dump PostgreSQL, mas este servidor está configurado com '$CURRENT_DB_KIND'. A restauração do banco será pulada — restaure só o que fizer sentido manualmente."
    HAS_DB_PG=0
fi
if [ "$HAS_DB_SQLITE" = "1" ] && [ "$CURRENT_DB_KIND" != "sqlite" ]; then
    warn "O pacote tem um banco SQLite, mas este servidor está configurado com '$CURRENT_DB_KIND'. A restauração do banco será pulada — restaure só o que fizer sentido manualmente."
    HAS_DB_SQLITE=0
fi

echo
warn "Isso vai SUBSTITUIR o banco de dados e as mídias enviadas atuais de $APP_DIR pelo conteúdo do pacote acima."
warn "O .env do pacote NÃO será aplicado — este servidor mantém suas próprias credenciais/domínio."
confirm "Confirma a restauração?" "n" || { info "Cancelado — nada foi alterado."; exit 0; }

# ---------------------------------------------------------------
# 2) Backup de segurança do estado atual, ANTES de sobrescrever
# ---------------------------------------------------------------
title "2/5 — Backup de segurança do estado atual"
SAFETY_RESULT="$(mktemp)"
bash "$SCRIPT_DIR/backup.sh" "$APP_DIR" "pre-restore" --result-file "$SAFETY_RESULT"
SAFETY_PKG="$(cat "$SAFETY_RESULT")"
rm -f "$SAFETY_RESULT"
ok "Estado atual salvo em $SAFETY_PKG — restaure esse pacote se algo der errado."

# ---------------------------------------------------------------
# 3) Parar o serviço antes de tocar no banco/arquivos
# ---------------------------------------------------------------
title "3/5 — Parando o serviço"
systemctl stop midia-indoor || true

# ---------------------------------------------------------------
# 4) Restaurar banco + uploads
# ---------------------------------------------------------------
title "4/5 — Restaurando dados"
if [ "$HAS_DB_SQLITE" = "1" ]; then
    DB_PATH="${DATABASE_URL#sqlite:///}"
    [[ "$DB_PATH" = /* ]] || DB_PATH="$APP_DIR/$DB_PATH"
    mkdir -p "$(dirname "$DB_PATH")"
    cp "$EXTRACTED_DIR/database.sqlite3" "$DB_PATH"
    ok "Banco SQLite restaurado."
elif [ "$HAS_DB_PG" = "1" ]; then
    need_cmd psql
    if psql "${DATABASE_URL/postgresql+psycopg2/postgresql}" -v ON_ERROR_STOP=1 -f "$EXTRACTED_DIR/database.sql" >"$WORK_DIR/psql.log" 2>&1; then
        ok "Banco PostgreSQL restaurado."
    else
        tail -40 "$WORK_DIR/psql.log" >&2
        systemctl start midia-indoor || true
        die "Falha ao restaurar o PostgreSQL (veja o log acima). O serviço foi religado com os dados antigos. Nada mais foi alterado."
    fi
else
    info "Sem dump de banco compatível no pacote — pulando restauração do banco."
fi

if [ -f "$EXTRACTED_DIR/uploads.tar.gz" ]; then
    UPLOAD_DIR="$APP_DIR/${UPLOAD_FOLDER:-app/static/uploads}"
    if [ -d "$UPLOAD_DIR" ]; then
        mv "$UPLOAD_DIR" "${UPLOAD_DIR}.antes-restore-$(date -u +%Y%m%d%H%M%S)"
    fi
    mkdir -p "$(dirname "$UPLOAD_DIR")"
    tar -xzf "$EXTRACTED_DIR/uploads.tar.gz" -C "$(dirname "$UPLOAD_DIR")"
    ok "Uploads restaurados (a pasta antiga foi renomeada para .antes-restore-*, não apagada)."
else
    info "Pacote sem uploads — pasta de mídias atual mantida como está."
fi

chown -R midia-indoor:midia-indoor "$APP_DIR"

# ---------------------------------------------------------------
# 5) Migrações + reiniciar + healthcheck
# ---------------------------------------------------------------
title "5/5 — Aplicando migrações e reiniciando"
export FLASK_APP=wsgi.py
if ! (cd "$APP_DIR" && "$APP_DIR/venv/bin/flask" db upgrade); then
    warn "Falha ao aplicar migrações após a restauração — o schema do pacote pode ser de uma versão diferente do código atual. Verifique manualmente antes de liberar o site."
fi

systemctl start midia-indoor
BIND="$(grep -E '^GUNICORN_BIND=' "$APP_DIR/.env" | cut -d= -f2- || true)"
BIND="${BIND:-127.0.0.1:8000}"
if wait_for_http "http://$BIND/healthz" 30; then
    ok "Restauração concluída — serviço no ar e respondendo em /healthz."
else
    err "Serviço reiniciado mas /healthz não respondeu em 30s. Verifique: sudo journalctl -u midia-indoor -n 100"
    err "Backup de segurança do estado anterior, se precisar desfazer: $SAFETY_PKG"
    exit 1
fi

echo
info "Backup de segurança do que havia ANTES desta restauração: $SAFETY_PKG"
