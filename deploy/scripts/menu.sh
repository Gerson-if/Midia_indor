#!/usr/bin/env bash
# =============================================================
# menu.sh — painel de controle interativo do Nexo Mídia. Ponto de
# entrada único para instalar, atualizar, fazer backup/restore,
# migrar de servidor e rodar comandos do dia a dia, sem precisar
# decorar o nome/caminho de cada script.
#
# Depois de instalado (install.sh cria isso automaticamente), basta:
#   sudo nexo
#
# Ou, direto do repositório, sem instalar o atalho:
#   sudo bash deploy/scripts/menu.sh [APP_DIR]
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root

# ---------------------------------------------------------------
# Descobrir o diretório da instalação. Ordem de preferência:
#   1) argumento passado na linha de comando
#   2) instalação padrão em /opt/midia-indoor
#   3) pergunta ao usuário (cobre instalações em outro caminho)
# ---------------------------------------------------------------
APP_DIR="${1:-}"
if [ -z "$APP_DIR" ]; then
    if [ -f "/opt/midia-indoor/wsgi.py" ]; then
        APP_DIR="/opt/midia-indoor"
    fi
fi

# Garante que $APP_DIR aponta para uma instalação válida antes de
# rodar qualquer ação que dependa dela. Retorna 1 (sem interromper
# o menu, graças ao "set -e" já não se aplicar a testes de retorno)
# se o usuário desistir de informar um caminho válido.
detect_or_ask_app_dir() {
    local tries=0
    while [ -z "$APP_DIR" ] || [ ! -f "$APP_DIR/wsgi.py" ]; do
        tries=$((tries + 1))
        if [ -n "$APP_DIR" ]; then
            warn "Não encontrei wsgi.py em '$APP_DIR' — esse não parece ser o diretório de uma instalação do Nexo Mídia."
        fi
        if [ "$tries" -gt 1 ] && ! confirm "Tentar outro caminho?" "s"; then
            APP_DIR=""
            return 1
        fi
        ask "Qual o diretório da instalação?" "/opt/midia-indoor" APP_DIR
    done
    return 0
}

banner() {
    echo -e "${C_BOLD}${C_CYAN}"
    cat <<'BANNER'
 _   _                 __  __ _     _
| \ | | _____  _____  |  \/  (_) __| (_) __ _
|  \| |/ _ \ \/ / _ \ | |\/| | |/ _` | |/ _` |
| |\  |  __/>  < (_) || |  | | | (_| | | (_| |
|_| \_|\___/_/\_\___/ |_|  |_|_|\__,_|_|\__,_|
              painel de controle
BANNER
    echo -e "${C_RESET}"
}

do_install() {
    if [ -n "$APP_DIR" ] && [ -f "$APP_DIR/wsgi.py" ]; then
        warn "Já existe uma instalação em $APP_DIR. Rodar install.sh de novo é seguro (idempotente) e serve para corrigir/completar uma instalação."
        confirm "Continuar mesmo assim?" "n" || return 0
        (cd "$APP_DIR" && bash "$APP_DIR/deploy/scripts/install.sh")
    else
        # Sem instalação ainda: o install.sh precisa rodar de dentro
        # da pasta com o código-fonte do projeto (clonado/extraído).
        local src="$PWD"
        if [ ! -f "$src/wsgi.py" ]; then
            err "Rode o instalador de dentro da pasta do projeto (onde está o wsgi.py), ex.:"
            err "  git clone <url-do-repositorio> midia-indoor && cd midia-indoor"
            err "  sudo bash deploy/scripts/install.sh"
            return 1
        fi
        bash "$src/deploy/scripts/install.sh"
    fi
    # depois de instalar, redescobre o APP_DIR pra continuar no menu
    [ -f "/opt/midia-indoor/wsgi.py" ] && APP_DIR="/opt/midia-indoor"
}

do_update() {
    bash "$SCRIPT_DIR/update.sh" "$APP_DIR"
}

do_backup() {
    ask "Rótulo curto para identificar este backup" "manual" TAG
    bash "$SCRIPT_DIR/backup.sh" "$APP_DIR" "$TAG"
}

do_list_backups() {
    title "Backups completos em $APP_DIR/backups/full"
    if [ -d "$APP_DIR/backups/full" ] && [ -n "$(ls -A "$APP_DIR/backups/full" 2>/dev/null)" ]; then
        ls -1t "$APP_DIR/backups/full"/backup-*.tar.gz 2>/dev/null | while read -r p; do
            echo "  $(du -h "$p" | cut -f1)  $(date -r "$p" '+%d/%m/%Y %H:%M')  $(basename "$p")"
        done
    else
        info "Nenhum backup completo ainda. Use a opção de Backup no menu para criar um."
    fi
}

do_restore() {
    bash "$SCRIPT_DIR/restore.sh" "$APP_DIR"
}

do_migrate() {
    bash "$SCRIPT_DIR/migrate.sh" "$APP_DIR"
}

do_rollback() {
    bash "$SCRIPT_DIR/rollback.sh" "$APP_DIR"
}

do_system_menu() {
    bash "$SCRIPT_DIR/system.sh" "$APP_DIR"
}

do_uninstall() {
    title "Desinstalar — Nexo Mídia"
    warn "Isso para e desativa a aplicação. Os dados (banco, uploads, .env) NÃO são apagados por padrão — ficam em $APP_DIR para você recuperar depois, ou restaurar numa instalação nova."
    confirm "Parar e desativar o serviço agora?" "n" || { info "Cancelado."; return 0; }

    if confirm "Antes de continuar, gerar um backup completo de segurança?" "s"; then
        bash "$SCRIPT_DIR/backup.sh" "$APP_DIR" "pre-uninstall"
    fi

    systemctl stop midia-indoor 2>/dev/null || true
    systemctl disable midia-indoor 2>/dev/null || true
    ok "Serviço midia-indoor parado e desativado."

    if command -v caddy >/dev/null 2>&1 && [ -f /etc/caddy/Caddyfile ]; then
        confirm "Também parar o Caddy (proxy/HTTPS)? Só faça isso se ele não estiver servindo outros sites nesta VPS." "n" \
            && { systemctl stop caddy 2>/dev/null || true; ok "Caddy parado."; }
    fi

    echo
    warn "O diretório $APP_DIR (código, .env, banco, uploads, backups) foi mantido intacto."
    echo "Para remover os dados também (${C_RED}irreversível${C_RESET}, mesmo com o backup gerado acima "
    echo "salvo dentro da própria pasta — copie-o para outro lugar antes se quiser mantê-lo):"
    echo "   sudo rm -rf $APP_DIR"
    echo "   sudo userdel midia-indoor"
    echo "   sudo rm -f /etc/systemd/system/midia-indoor.service && sudo systemctl daemon-reload"
}

main_menu() {
    while true; do
        banner
        echo -e "  Instalação atual: ${C_BOLD}${APP_DIR:-<nenhuma encontrada>}${C_RESET}\n"
        choose "O que você quer fazer?" OPT \
            "Instalar (nova instalação, ou corrigir uma existente)" \
            "Atualizar (publicar a última versão do código)" \
            "Backup completo agora" \
            "Listar backups" \
            "Restaurar um backup" \
            "Migrar para um servidor novo" \
            "Reverter para uma versão de código anterior" \
            "Comandos do sistema (status, logs, reiniciar, firewall...)" \
            "Desinstalar" \
            "Sair"
        echo
        # Cada ação roda protegida por "|| true": se o script chamado
        # falhar (erro real, ou o usuário cancelar uma confirmação),
        # o menu volta a aparecer em vez de derrubar o painel inteiro
        # por causa do "set -e". A mensagem de erro do script chamado
        # já fica visível na tela antes de voltar.
        case "$OPT" in
            "Instalar (nova instalação, ou corrigir uma existente)")
                do_install || true ;;
            "Atualizar (publicar a última versão do código)")
                detect_or_ask_app_dir && do_update || true ;;
            "Backup completo agora")
                detect_or_ask_app_dir && do_backup || true ;;
            "Listar backups")
                detect_or_ask_app_dir && do_list_backups || true ;;
            "Restaurar um backup")
                detect_or_ask_app_dir && do_restore || true ;;
            "Migrar para um servidor novo")
                detect_or_ask_app_dir && do_migrate || true ;;
            "Reverter para uma versão de código anterior")
                detect_or_ask_app_dir && do_rollback || true ;;
            "Comandos do sistema (status, logs, reiniciar, firewall...)")
                detect_or_ask_app_dir && do_system_menu || true ;;
            "Desinstalar")
                detect_or_ask_app_dir && do_uninstall || true ;;
            "Sair") exit 0 ;;
        esac
        echo
        read -r -p "Pressione Enter para voltar ao menu..." _ || true
    done
}

main_menu
