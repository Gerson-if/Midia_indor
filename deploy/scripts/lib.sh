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
    local prompt="$1" default="$2" __resultvar="$3" __ask_input
    if [ -n "$default" ]; then
        read -r -p "$(echo -e "${C_BOLD}?${C_RESET} ${prompt} [${default}]: ")" __ask_input
        __ask_input="${__ask_input:-$default}"
    else
        while true; do
            read -r -p "$(echo -e "${C_BOLD}?${C_RESET} ${prompt}: ")" __ask_input
            [ -n "$__ask_input" ] && break
            warn "Este valor não pode ficar em branco."
        done
    fi
    printf -v "$__resultvar" '%s' "$__ask_input"
}

# Pergunta com valor secreto (não ecoa na tela). Uso: ask_secret "Pergunta" VAR_NAME
ask_secret() {
    local prompt="$1" __resultvar="$2" __ask_input
    while true; do
        read -r -s -p "$(echo -e "${C_BOLD}?${C_RESET} ${prompt}: ")" __ask_input
        echo
        [ -n "$__ask_input" ] && break
        warn "Este valor não pode ficar em branco."
    done
    printf -v "$__resultvar" '%s' "$__ask_input"
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
    local __choose_input
    while true; do
        read -r -p "   Escolha [1-${#opts[@]}]: " __choose_input
        if [[ "$__choose_input" =~ ^[0-9]+$ ]] && [ "$__choose_input" -ge 1 ] && [ "$__choose_input" -le "${#opts[@]}" ]; then
            printf -v "$__resultvar" '%s' "${opts[$((__choose_input - 1))]}"
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

# ---------------------------------------------------------------
# Validadores de entrada (usados por configure-env.sh e install.sh
# para pegar erros de digitação ANTES de gravar o .env, em vez de
# só descobrir o problema minutos depois numa etapa mais adiante)
# ---------------------------------------------------------------
is_valid_domain() {
    local d="$1"
    [[ "$d" =~ ^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$ ]]
}

is_valid_email() {
    local e="$1"
    [[ "$e" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]
}

# Pergunta com valor padrão, mas repete até o validador (função cujo
# nome é passado em $4) aceitar. Uso:
#   ask_validated "Domínio" "" DOMAIN is_valid_domain "formato inválido"
ask_validated() {
    local prompt="$1" default="$2" __resultvar="$3" validator="$4" hint="${5:-valor inválido}"
    local reply
    while true; do
        ask "$prompt" "$default" reply
        if "$validator" "$reply"; then
            printf -v "$__resultvar" '%s' "$reply"
            return 0
        fi
        warn "$hint: '$reply'"
    done
}

# Atualiza (ou adiciona, se ainda não existir) uma única variável num
# arquivo .env, sem tocar no resto do arquivo -- usado por ações do menu
# que trocam uma credencial isolada (ex.: redefinir senha do admin/super
# admin) sem precisar reconfigurar tudo de novo via configure-env.sh.
# Reescreve o arquivo inteiro via arquivo temporário (em vez de sed -i
# no lugar) para preservar dono/permissões (600, midia-indoor:midia-indoor)
# e evitar problemas de delimitador do sed se o valor contiver caracteres
# especiais (ex.: senha gerada aleatoriamente). Uso:
#   set_env_var "$APP_DIR/.env" ADMIN_PASSWORD "$NOVA_SENHA"
set_env_var() {
    local env_file="$1" key="$2" value="$3" tmp owner
    tmp="$(mktemp)"
    grep -v "^${key}=" "$env_file" 2>/dev/null >"$tmp" || true
    printf '%s="%s"\n' "$key" "${value//\"/\\\"}" >>"$tmp"
    chmod 600 "$tmp"
    owner="$(stat -c '%U:%G' "$env_file" 2>/dev/null || true)"
    [ -n "$owner" ] && chown "$owner" "$tmp" 2>/dev/null || true
    mv "$tmp" "$env_file"
}

# Roda um comando com algumas tentativas, com pausa entre elas —
# apt/curl em VPS novas falham às vezes por lentidão momentânea de
# rede/DNS/mirror, e sem retry isso derruba a instalação inteira por
# um problema transitório que teria passado na 2ª tentativa.
retry() {
    local max="$1" delay="$2"
    shift 2
    local attempt=1
    until "$@"; do
        if [ "$attempt" -ge "$max" ]; then
            err "Comando falhou após $max tentativas: $*"
            return 1
        fi
        warn "Falhou (tentativa $attempt/$max). Tentando de novo em ${delay}s..."
        sleep "$delay"
        attempt=$((attempt + 1))
    done
}

# Espera um endpoint HTTP local responder 2xx/3xx, com timeout total.
# Uso: wait_for_http "http://127.0.0.1:8000/healthz" 30
wait_for_http() {
    local url="$1" timeout="${2:-30}" waited=0
    while [ "$waited" -lt "$timeout" ]; do
        if curl -fsS --max-time 3 -o /dev/null "$url" 2>/dev/null; then
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    return 1
}

# Confere se a porta TCP já está em uso por outro processo (comum:
# Apache/Nginx padrão da distro ocupando 80/443 antes do Caddy).
port_in_use() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        ss -ltn "( sport = :$port )" 2>/dev/null | grep -q ":$port"
    else
        (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null && { exec 3>&-; return 0; } || return 1
    fi
}
