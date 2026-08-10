#!/usr/bin/env bash
# =============================================================
# migrate.sh — assistente de migração para uma VPS nova. Gera um
# pacote de backup completo (via backup.sh, tag "migration") e,
# se você quiser, já envia por SSH/scp para o servidor novo —
# depois mostra exatamente os comandos a rodar lá para concluir.
#
# Este script SÓ RODA NO SERVIDOR ANTIGO (origem). O servidor novo
# recebe o pacote e usa install.sh + restore.sh normalmente — não
# existe um passo "mágico" separado no destino, é o mesmo fluxo
# guiado de sempre, só que restaurando dados de outro lugar.
#
# Uso:
#   sudo bash deploy/scripts/migrate.sh [APP_DIR]
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root

APP_DIR="${1:-/opt/midia-indoor}"
[ -f "$APP_DIR/wsgi.py" ] || die "Não encontrei wsgi.py em $APP_DIR."

title "Migração para um servidor novo — Nexo Mídia"

info "Este assistente NÃO altera o servidor atual. Ele apenas:"
echo "   1) gera um pacote de backup completo (banco + uploads);"
echo "   2) opcionalmente envia esse pacote por SSH para a VPS nova;"
echo "   3) mostra o passo a passo para concluir a migração lá."
echo

REPO_URL=""
if [ -d "$APP_DIR/.git" ]; then
    REPO_URL="$(git -C "$APP_DIR" remote get-url origin 2>/dev/null || true)"
fi

title "1/3 — Gerando o pacote de backup"
RESULT_TMP="$(mktemp)"
bash "$SCRIPT_DIR/backup.sh" "$APP_DIR" "migration" --result-file "$RESULT_TMP"
PKG_PATH="$(cat "$RESULT_TMP")"
rm -f "$RESULT_TMP"
PKG_NAME="$(basename "$PKG_PATH")"
ok "Pacote pronto: $PKG_PATH"

title "2/3 — Enviar para o servidor novo agora?"
if confirm "Você já tem acesso SSH (usuário + IP/host) ao servidor novo e quer enviar o pacote agora?" "n"; then
    ask "Usuário SSH no servidor novo" "root" SSH_USER
    ask "IP ou host do servidor novo" "" SSH_HOST
    ask "Porta SSH" "22" SSH_PORT
    ask "Pasta de destino no servidor novo" "/root/" REMOTE_DIR

    info "Enviando $PKG_NAME (isso pode demorar dependendo do tamanho/rede)..."
    if scp -P "$SSH_PORT" "$PKG_PATH" "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR%/}/"; then
        ok "Pacote enviado para ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR%/}/${PKG_NAME}"
        SENT=1
        REMOTE_PKG_PATH="${REMOTE_DIR%/}/${PKG_NAME}"
    else
        err "Falha ao enviar via scp. Copie manualmente com o comando mostrado abaixo."
        SENT=0
    fi
else
    SENT=0
fi

title "3/3 — Passo a passo no servidor novo"
echo -e "${C_BOLD}No servidor NOVO, como root/sudo:${C_RESET}"
echo
if [ "${SENT:-0}" != "1" ]; then
    echo "0) Copie o pacote de backup para lá, por exemplo:"
    echo "   scp \"$PKG_PATH\" usuario@IP-DO-SERVIDOR-NOVO:/root/"
    echo
fi
STEP=1
if [ -n "$REPO_URL" ]; then
    echo "$STEP) Clone o repositório e instale normalmente:"
    echo "   git clone $REPO_URL midia-indoor && cd midia-indoor"
    echo "   sudo bash deploy/scripts/install.sh"
else
    echo "$STEP) Envie o código do projeto (git clone ou .zip) e instale normalmente:"
    echo "   sudo bash deploy/scripts/install.sh"
fi
STEP=$((STEP + 1))
echo "   -> responda as perguntas do instalador normalmente: domínio,"
echo "      banco, admin, etc. Cada servidor gera SUAS PRÓPRIAS"
echo "      credenciais (SECRET_KEY, senha do banco) — não copie as"
echo "      credenciais do servidor antigo."
echo
echo "$STEP) Depois que a instalação terminar (site já no ar, mesmo que"
echo "   com conteúdo vazio/demo), restaure os dados do pacote:"
if [ "${SENT:-0}" = "1" ]; then
    echo "   sudo bash /opt/midia-indoor/deploy/scripts/restore.sh /opt/midia-indoor \\"
    echo "       \"$REMOTE_PKG_PATH\""
else
    echo "   sudo bash /opt/midia-indoor/deploy/scripts/restore.sh /opt/midia-indoor \\"
    echo "       /root/$PKG_NAME"
fi
echo
echo "   O restore.sh substitui o banco e os uploads do servidor novo"
echo "   pelos do pacote, SEM mexer no .env recém-gerado (domínio e"
echo "   credenciais do servidor novo continuam sendo os dele)."
echo
echo "   Se o domínio for o mesmo de antes, atualize o DNS (registro A)"
echo "   para apontar para o IP do servidor NOVO — o Caddy emite o"
echo "   certificado HTTPS automaticamente assim que o DNS propagar."
echo
ok "Pacote de migração: $PKG_PATH"
