#!/usr/bin/env bash
# =============================================================
# lib.sh — funções compartilhadas pelos scripts de deploy do
# Nexo Mídia. Não execute este arquivo diretamente: ele é
# carregado (source) pelos outros scripts em deploy/scripts/.
# =============================================================
set -euo pipefail

# ---- Cores ----
C_RESET="\033[0m"
C_BOLD="\033[1m"
C_GREEN="\033[32m"
C_YELLOW="\033[33m"
C_RED="\033[31m"
C_CYAN="\033[36m"

info()  { echo -e "${C_CYAN}➜${C_RESET} $*"; }
ok()    { echo -e "${C_GREEN}✔${C_RESET} $*"; }
warn()  { echo -e "${C_YELLOW}⚠${C_RESET} $*"; }
err()   { echo -e "${C_RED}✘${C_RESET} $*" >&2; }
title() { echo -e "\n${C_BOLD}${C_CYAN}== $* ==${C_RESET}\n"; }

die() {
    err "$*"
    exit 1
}

need_root() {
    if [ "$(id -u)" -ne 0 ]; then
        die "Este script precisa ser executado com sudo/root. Ex.: sudo $0"
    fi
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Comando obrigatório não encontrado: $1"
}

# Pergunta simples com valor padrão. Uso: ask "Pergunta" "padrao" VAR_NAME
ask() {
    local prompt="$1" default="$2" __resultvar="$3" reply
    if [ -n "$default" ]; then
        read -r -p "$(echo -e "${C_BOLD}?${C_RESET} ${prompt} [${default}]: ")" reply
        reply="${reply:-$default}"
    else
        while true; do
            read -r -p "$(echo -e "${C_BOLD}?${C_RESET} ${prompt}: ")" reply
            [ -n "$reply" ] && break
            warn "Este valor não pode ficar em branco."
        done
    fi
    printf -v "$__resultvar" '%s' "$reply"
}

# Pergunta com valor secreto (não ecoa na tela). Uso: ask_secret "Pergunta" VAR_NAME
ask_secret() {
    local prompt="$1" __resultvar="$2" reply
    while true; do
        read -r -s -p "$(echo -e "${C_BOLD}?${C_RESET} ${prompt}: ")" reply
        echo
        [ -n "$reply" ] && break
        warn "Este valor não pode ficar em branco."
    done
    printf -v "$__resultvar" '%s' "$reply"
}

# Pergunta sim/não. Uso: if confirm "Continuar?" "s"; then ...
confirm() {
    local prompt="$1" default="${2:-s}" reply hint
    if [ "$default" = "s" ]; then hint="S/n"; else hint="s/N"; fi
    read -r -p "$(echo -e "${C_BOLD}?${C_RESET} ${prompt} [${hint}]: ")" reply
    reply="${reply:-$default}"
    [[ "$reply" =~ ^[sSyY] ]]
}

# Menu de escolha numerada. Uso: choose "Pergunta" VAR_NAME "Opção 1" "Opção 2" ...
choose() {
    local prompt="$1" __resultvar="$2"
    shift 2
    local opts=("$@")
    echo -e "${C_BOLD}?${C_RESET} ${prompt}"
    local i=1
    for o in "${opts[@]}"; do
        echo "   $i) $o"
        i=$((i + 1))
    done
    local reply
    while true; do
        read -r -p "   Escolha [1-${#opts[@]}]: " reply
        if [[ "$reply" =~ ^[0-9]+$ ]] && [ "$reply" -ge 1 ] && [ "$reply" -le "${#opts[@]}" ]; then
            printf -v "$__resultvar" '%s' "${opts[$((reply - 1))]}"
            return 0
        fi
        warn "Opção inválida."
    done
}

gen_secret() {
    python3 -c "import secrets; print(secrets.token_hex(32))"
}

# Valida um IPv4 simples.
is_ipv4() {
    local ip="$1"
    [[ "$ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1
    local IFS='.'
    read -r -a parts <<<"$ip"
    for p in "${parts[@]}"; do
        [ "$p" -le 255 ] || return 1
    done
    return 0
}

detect_public_ip() {
    curl -fsSL --max-time 3 https://api.ipify.org 2>/dev/null \
        || curl -fsSL --max-time 3 https://ifconfig.me 2>/dev/null \
        || hostname -I 2>/dev/null | awk '{print $1}' \
        || echo ""
}
