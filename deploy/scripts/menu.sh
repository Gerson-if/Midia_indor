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

# ---------------------------------------------------------------
# Definir/redefinir credenciais (admin de página ou super admin) —
# sem precisar reconfigurar o .env inteiro nem lembrar os comandos
# "flask create-admin"/"flask create-superadmin" de cor.
# ---------------------------------------------------------------
do_set_admin_credentials() {
    title "Definir/redefinir administrador de uma página"

    set -a
    # shellcheck disable=SC1091
    source "$APP_DIR/.env"
    set +a

    ask "Slug da página" "default" TENANT_SLUG_INPUT
    if [ "$TENANT_SLUG_INPUT" != "default" ]; then
        info "Páginas além da 'default' (multi-tenant) normalmente são geridas pelo painel do super admin em /super — use esta opção só se souber o slug exato da página."
    fi

    ask_validated "E-mail do administrador (login)" "${ADMIN_EMAIL:-}" NEW_ADMIN_EMAIL \
        is_valid_email "E-mail com formato inválido"

    if confirm "Gerar uma senha forte automaticamente?" "s"; then
        NEW_ADMIN_PASSWORD="$(gen_secret | cut -c1-16)"
        ok "Senha gerada: ${C_BOLD}${NEW_ADMIN_PASSWORD}${C_RESET} (anote agora — não será mostrada de novo)"
    else
        while true; do
            ask_secret "Nova senha (mínimo 12 caracteres)" NEW_ADMIN_PASSWORD
            [ "${#NEW_ADMIN_PASSWORD}" -ge 12 ] && break
            warn "Senha muito curta (${#NEW_ADMIN_PASSWORD} caracteres) — use pelo menos 12."
        done
    fi

    (
        export FLASK_APP=wsgi.py
        export ADMIN_NAME="${ADMIN_NAME:-Administrador}"
        export ADMIN_EMAIL="$NEW_ADMIN_EMAIL"
        export ADMIN_PASSWORD="$NEW_ADMIN_PASSWORD"
        cd "$APP_DIR" && "$APP_DIR/venv/bin/flask" create-admin --tenant-slug "$TENANT_SLUG_INPUT"
    ) || { err "Falha ao definir o administrador — veja o erro acima."; return 1; }

    ok "Administrador da página '$TENANT_SLUG_INPUT' atualizado: $NEW_ADMIN_EMAIL"

    if [ "$TENANT_SLUG_INPUT" = "default" ]; then
        if confirm "Salvar esse e-mail/senha em $APP_DIR/.env? (recomendado — sem isso, a próxima atualização/update.sh volta a usar as credenciais antigas do .env)" "s"; then
            set_env_var "$APP_DIR/.env" ADMIN_EMAIL "$NEW_ADMIN_EMAIL"
            set_env_var "$APP_DIR/.env" ADMIN_PASSWORD "$NEW_ADMIN_PASSWORD"
            ok ".env atualizado."
        fi
    else
        info "Página '$TENANT_SLUG_INPUT' não é a 'default' — essas credenciais não vivem no .env (só o admin da página 'default' vive); nada a salvar aqui."
    fi
}

do_set_superadmin_credentials() {
    title "Definir/redefinir super admin"

    set -a
    # shellcheck disable=SC1091
    source "$APP_DIR/.env"
    set +a

    ask_validated "E-mail do super admin (login em /super)" "${SUPERADMIN_EMAIL:-}" NEW_SUPERADMIN_EMAIL \
        is_valid_email "E-mail com formato inválido"

    if confirm "Gerar uma senha forte automaticamente?" "s"; then
        NEW_SUPERADMIN_PASSWORD="$(gen_secret | cut -c1-16)"
        ok "Senha gerada: ${C_BOLD}${NEW_SUPERADMIN_PASSWORD}${C_RESET} (anote agora — não será mostrada de novo)"
    else
        while true; do
            ask_secret "Nova senha (mínimo 12 caracteres)" NEW_SUPERADMIN_PASSWORD
            [ "${#NEW_SUPERADMIN_PASSWORD}" -ge 12 ] && break
            warn "Senha muito curta (${#NEW_SUPERADMIN_PASSWORD} caracteres) — use pelo menos 12."
        done
    fi

    (
        export FLASK_APP=wsgi.py
        export SUPERADMIN_NAME="${SUPERADMIN_NAME:-Super Admin}"
        export SUPERADMIN_EMAIL="$NEW_SUPERADMIN_EMAIL"
        export SUPERADMIN_PASSWORD="$NEW_SUPERADMIN_PASSWORD"
        cd "$APP_DIR" && "$APP_DIR/venv/bin/flask" create-superadmin
    ) || { err "Falha ao definir o super admin — veja o erro acima."; return 1; }

    ok "Super admin atualizado: $NEW_SUPERADMIN_EMAIL (painel: /super/login)"

    if confirm "Salvar esse e-mail/senha em $APP_DIR/.env? (recomendado)" "s"; then
        set_env_var "$APP_DIR/.env" SUPERADMIN_NAME "${SUPERADMIN_NAME:-Super Admin}"
        set_env_var "$APP_DIR/.env" SUPERADMIN_EMAIL "$NEW_SUPERADMIN_EMAIL"
        set_env_var "$APP_DIR/.env" SUPERADMIN_PASSWORD "$NEW_SUPERADMIN_PASSWORD"
        ok ".env atualizado."
    fi
}

do_set_credentials() {
    choose "Redefinir credenciais de quem?" WHO \
        "Administrador de uma página" \
        "Super admin (painel /super)"
    case "$WHO" in
        "Administrador de uma página") do_set_admin_credentials ;;
        "Super admin (painel /super)") do_set_superadmin_credentials ;;
    esac
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
            "Definir/redefinir usuário e senha (admin de página ou super admin)" \
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
            "Definir/redefinir usuário e senha (admin de página ou super admin)")
                detect_or_ask_app_dir && do_set_credentials || true ;;
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
