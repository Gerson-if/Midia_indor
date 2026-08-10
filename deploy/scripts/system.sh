#!/usr/bin/env bash
# =============================================================
# system.sh — submenu de comandos rápidos do dia a dia (status,
# reiniciar, ver logs, healthcheck, firewall, reconfigurar .env).
# Chamado pelo menu.sh, mas também roda standalone:
#   sudo bash deploy/scripts/system.sh [APP_DIR]
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root
APP_DIR="${1:-/opt/midia-indoor}"

healthcheck() {
    local bind url
    bind="$(grep -E '^GUNICORN_BIND=' "$APP_DIR/.env" 2>/dev/null | cut -d= -f2- || true)"
    bind="${bind:-127.0.0.1:8000}"
    url="http://$bind/healthz"
    info "Checando $url ..."
    if curl -fsS --max-time 5 "$url"; then
        echo
        ok "Respondeu OK."
    else
        echo
        err "Não respondeu. Veja: sudo journalctl -u midia-indoor -n 100"
    fi
}

show_status() {
    title "Status dos serviços"
    echo -e "${C_BOLD}midia-indoor (aplicação):${C_RESET}"
    systemctl status midia-indoor --no-pager -l | head -12 || true
    echo
    if systemctl list-unit-files caddy.service >/dev/null 2>&1; then
        echo -e "${C_BOLD}caddy (proxy/HTTPS):${C_RESET}"
        systemctl status caddy --no-pager -l | head -8 || true
        echo
    fi
    healthcheck
    echo
    if [ -d "$APP_DIR/.git" ]; then
        echo -e "${C_BOLD}Versão do código:${C_RESET}"
        git -C "$APP_DIR" log -1 --format='  %h — %s (%cr)' || true
    fi
}

restart_service() {
    confirm "Reiniciar o serviço midia-indoor agora? Isso derruba conexões em andamento por 1-2s." "s" || return 0
    systemctl restart midia-indoor
    sleep 2
    healthcheck
}

reload_service() {
    info "Recarregando sem downtime (mesma técnica usada pelo update.sh)..."
    systemctl reload midia-indoor
    sleep 2
    healthcheck
}

tail_logs() {
    info "Mostrando logs em tempo real — Ctrl+C para voltar ao menu."
    trap 'trap - INT; return 0' INT
    journalctl -u midia-indoor -f --no-pager || true
    trap - INT
}

toggle_firewall() {
    if ! command -v ufw >/dev/null 2>&1; then
        if confirm "UFW não está instalado. Instalar agora?" "s"; then
            apt-get update -y >/dev/null && apt-get install -y ufw >/dev/null
        else
            return 0
        fi
    fi
    title "Firewall (UFW)"
    ufw status verbose || true
    echo
    choose "O que fazer?" ACTION \
        "Liberar SSH + HTTP + HTTPS e ativar o UFW" \
        "Desativar o UFW" \
        "Voltar"
    case "$ACTION" in
        "Liberar SSH + HTTP + HTTPS e ativar o UFW")
            ufw allow OpenSSH >/dev/null || true
            ufw allow 80/tcp >/dev/null || true
            ufw allow 443/tcp >/dev/null || true
            yes | ufw enable >/dev/null
            ok "UFW ativo com SSH/80/443 liberados."
            ;;
        "Desativar o UFW")
            confirm "Tem certeza? Isso remove a proteção de firewall desta VPS." "n" && ufw disable >/dev/null && ok "UFW desativado."
            ;;
        *) ;;
    esac
}

reconfigure_env() {
    warn "Isso vai reabrir o assistente de configuração do .env (domínio, banco, admin, etc). Valores atuais aparecem como padrão."
    confirm "Continuar?" "s" || return 0
    bash "$SCRIPT_DIR/configure-env.sh" "$APP_DIR/.env"
    confirm "Reiniciar o serviço para aplicar as mudanças agora?" "s" && { systemctl restart midia-indoor; sleep 2; healthcheck; }
}

disk_usage() {
    title "Uso de disco"
    echo -e "${C_BOLD}Partição:${C_RESET}"
    df -h "$APP_DIR" | awk 'NR==1 || NR==2'
    echo
    echo -e "${C_BOLD}Maiores pastas dentro de $APP_DIR:${C_RESET}"
    du -sh "$APP_DIR"/*/ 2>/dev/null | sort -rh | head -10
    echo
    if [ -d "$APP_DIR/backups" ]; then
        echo -e "${C_BOLD}Backups:${C_RESET}"
        du -sh "$APP_DIR/backups" 2>/dev/null
        [ -d "$APP_DIR/backups/full" ] && ls -1t "$APP_DIR/backups/full" 2>/dev/null | wc -l | xargs -I{} echo "  {} pacote(s) completo(s) em backups/full"
    fi
}

main_menu() {
    while true; do
        echo
        title "Comandos do sistema — $APP_DIR"
        choose "Escolha uma ação" OPT \
            "Status geral (serviços + healthcheck + versão)" \
            "Reiniciar aplicação" \
            "Recarregar sem downtime (reload)" \
            "Ver logs em tempo real" \
            "Healthcheck rápido" \
            "Uso de disco" \
            "Firewall (UFW)" \
            "Reconfigurar .env (domínio, banco, admin...)" \
            "Voltar"
        case "$OPT" in
            "Status geral (serviços + healthcheck + versão)") show_status || true ;;
            "Reiniciar aplicação") restart_service || true ;;
            "Recarregar sem downtime (reload)") reload_service || true ;;
            "Ver logs em tempo real") tail_logs || true ;;
            "Healthcheck rápido") healthcheck || true ;;
            "Uso de disco") disk_usage || true ;;
            "Firewall (UFW)") toggle_firewall || true ;;
            "Reconfigurar .env (domínio, banco, admin...)") reconfigure_env || true ;;
            "Voltar") return 0 ;;
        esac
        echo
        read -r -p "Pressione Enter para continuar..." _ || true
    done
}

main_menu
