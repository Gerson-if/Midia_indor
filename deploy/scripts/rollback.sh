#!/usr/bin/env bash
# =============================================================
# rollback.sh — volta manualmente para um commit anterior.
# O update.sh já reverte sozinho se a atualização falhar; use
# este script quando quiser voltar atrás por outro motivo (bug
# percebido depois que tudo parecia ok).
#
# Só funciona em instalações com histórico git (veja install.sh).
# Sem git, restaure o backup mais recente em <APP_DIR>/backups/.
#
# Uso:
#   sudo bash deploy/scripts/rollback.sh [/opt/midia-indoor]
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root
APP_DIR="${1:-/opt/midia-indoor}"

[ -d "$APP_DIR/.git" ] || die "$APP_DIR não tem histórico git. Restaure manualmente pelo backup em $APP_DIR/backups/."

title "Rollback — Nexo Mídia"
echo "Últimos commits:"
git -C "$APP_DIR" log --oneline -10

read -r -p "Informe o hash do commit para o qual voltar: " TARGET
git -C "$APP_DIR" cat-file -e "$TARGET" 2>/dev/null || die "Commit inválido."

confirm "Confirma reverter $APP_DIR para $TARGET? Isso reinicia o serviço." "s" || exit 0

git -C "$APP_DIR" reset --hard "$TARGET"
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
(cd "$APP_DIR" && "$APP_DIR/venv/bin/flask" db upgrade) || warn "Migração não aplicada — verifique manualmente se o schema é compatível com $TARGET."
systemctl restart midia-indoor
sleep 2

BIND="$(grep -E '^GUNICORN_BIND=' "$APP_DIR/.env" | cut -d= -f2- || true)"
BIND="${BIND:-127.0.0.1:8000}"
if curl -fsS "http://$BIND/healthz" >/dev/null 2>&1; then
    ok "Rollback concluído. Commit ativo: $TARGET"
else
    err "Serviço reiniciado mas /healthz não respondeu. Verifique: sudo journalctl -u midia-indoor -n 100"
fi
