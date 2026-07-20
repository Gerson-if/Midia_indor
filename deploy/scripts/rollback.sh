#!/usr/bin/env bash
# =============================================================
# rollback.sh — volta manualmente para uma release anterior.
# O update.sh já faz rollback automático se a atualização falhar;
# use este script quando quiser voltar atrás por outro motivo
# (ex.: bug percebido depois que tudo parecia estar ok).
#
# Uso:
#   sudo bash deploy/scripts/rollback.sh [/opt/midia-indoor]
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root
APP_DIR="${1:-/opt/midia-indoor}"

[ -L "$APP_DIR/current" ] || die "$APP_DIR/current não encontrado."
CURRENT="$(readlink -f "$APP_DIR/current")"

mapfile -t RELEASES < <(ls -1dt "$APP_DIR"/releases/*/ 2>/dev/null | sed 's:/$::')
[ "${#RELEASES[@]}" -ge 2 ] || die "Não há release anterior para reverter."

title "Rollback — Nexo Mídia"
info "Release ativa agora: $(basename "$CURRENT")"
echo "Releases disponíveis:"
i=1
for r in "${RELEASES[@]}"; do
    marker=""
    [ "$r" = "$CURRENT" ] && marker=" (ativa)"
    echo "   $i) $(basename "$r")$marker"
    i=$((i + 1))
done

read -r -p "Escolha o número da release para ativar: " CHOICE
[[ "$CHOICE" =~ ^[0-9]+$ ]] && [ "$CHOICE" -ge 1 ] && [ "$CHOICE" -le "${#RELEASES[@]}" ] || die "Opção inválida."
TARGET="${RELEASES[$((CHOICE - 1))]}"

if [ "$TARGET" = "$CURRENT" ]; then
    warn "Essa já é a release ativa. Nada a fazer."
    exit 0
fi

confirm "Confirma reverter para $(basename "$TARGET")? Isso reinicia o serviço." "s" || exit 0

ln -sfn "$TARGET" "$APP_DIR/current"
systemctl restart midia-indoor
sleep 2

BIND="$(grep -E '^GUNICORN_BIND=' "$APP_DIR/shared/.env" | cut -d= -f2- || true)"
BIND="${BIND:-127.0.0.1:8000}"
if curl -fsS "http://$BIND/healthz" >/dev/null 2>&1; then
    ok "Rollback concluído. Release ativa: $(basename "$TARGET")"
else
    err "Serviço reiniciado mas /healthz não respondeu. Verifique: sudo journalctl -u midia-indoor -n 100"
fi
