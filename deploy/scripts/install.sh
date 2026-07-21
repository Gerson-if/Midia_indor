#!/usr/bin/env bash
# =============================================================
# install.sh — instalação guiada do Nexo Mídia em uma VPS Ubuntu,
# SEM Docker: Python + venv + Gunicorn + systemd + Nginx.
#
# Como usar (na VPS, dentro da pasta do projeto já extraída/clonada):
#   sudo bash deploy/scripts/install.sh
#
# O script é idempotente: pode ser executado de novo com segurança.
#
# Estrutura criada em /opt/midia-indoor — UMA PASTA SÓ, sem
# releases/current/shared. É o próprio código (git clone ou cópia
# do zip), com venv/.env/uploads/logs/instance vivendo dentro dela
# (esses já são ignorados pelo .gitignore, então um `git pull`
# nunca mexe neles):
#
#   /opt/midia-indoor/
#   ├── venv/                  -> ambiente virtual Python
#   ├── .env                   -> variáveis de ambiente
#   ├── app/static/uploads/    -> mídias enviadas pelo painel
#   ├── instance/              -> banco SQLite, se usado
#   └── logs/                  -> logs da aplicação
#
# Atualizações depois: deploy/scripts/update.sh (veja deploy/README.md)
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root

# Diretório onde o instalador foi extraído/clonado (raiz do projeto)
SOURCE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
[ -f "$SOURCE_DIR/wsgi.py" ] || die "Não encontrei wsgi.py em $SOURCE_DIR — rode este script de dentro do projeto."

APP_USER="midia-indoor"
APP_GROUP="midia-indoor"

echo -e "${C_BOLD}${C_CYAN}"
cat <<'BANNER'
 _   _                 __  __ _     _ _
| \ | | _____  _____  |  \/  (_) __| (_) __ _
|  \| |/ _ \ \/ / _ \ | |\/| | |/ _` | |/ _` |
| |\  |  __/>  < (_) || |  | | | (_| | | (_| |
|_| \_|\___/_/\_\___/ |_|  |_|_|\__,_|_|\__,_|
BANNER
echo -e "${C_RESET}"
title "Instalação guiada — deploy nativo no Ubuntu (sem Docker)"

ask "Em qual diretório instalar a aplicação?" "/opt/midia-indoor" APP_DIR

# ---------------------------------------------------------------
# 1) Pacotes do sistema
# ---------------------------------------------------------------
title "1/8 — Instalando pacotes do sistema (apt)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip python3-dev \
    build-essential libpq-dev libmagic1 libjpeg-dev zlib1g-dev \
    nginx git curl rsync ca-certificates gnupg

if confirm "Este projeto usará PostgreSQL (recomendado em produção)?" "s"; then
    apt-get install -y --no-install-recommends postgresql postgresql-contrib
    systemctl enable --now postgresql
fi

if confirm "Instalar Redis (recomendado para rate limiting em produção)?" "s"; then
    apt-get install -y --no-install-recommends redis-server
    systemctl enable --now redis-server
fi

if confirm "Ativar HTTPS automático (Let's Encrypt) mais adiante, se você tiver domínio?" "s"; then
    apt-get install -y --no-install-recommends certbot python3-certbot-nginx
fi

BUILD_FRONTEND=0
if confirm "Construir os assets de front-end (Tailwind CSS) agora? (requer Node.js/npm)" "s"; then
    if ! command -v npm >/dev/null 2>&1; then
        info "Node.js não encontrado — instalando (NodeSource, LTS)..."
        curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - >/dev/null
        apt-get install -y --no-install-recommends nodejs
    fi
    BUILD_FRONTEND=1
fi
ok "Pacotes do sistema prontos."

# ---------------------------------------------------------------
# 2) Usuário de sistema
# ---------------------------------------------------------------
title "2/8 — Usuário de sistema"
if ! id "$APP_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin --create-home "$APP_USER"
    ok "Usuário de sistema '$APP_USER' criado."
else
    ok "Usuário de sistema '$APP_USER' já existe."
fi

# ---------------------------------------------------------------
# 3) Publicar o código em APP_DIR (pasta única, sem releases)
# ---------------------------------------------------------------
title "3/8 — Publicando o código em $APP_DIR"
if [ "$SOURCE_DIR" = "$APP_DIR" ]; then
    ok "Já rodando de dentro de $APP_DIR — nada para copiar."
else
    mkdir -p "$APP_DIR"
    rsync -a \
        --exclude ".git" --exclude ".github" \
        --exclude "__pycache__" --exclude "*.pyc" \
        --exclude "node_modules" --exclude ".env" \
        --exclude "instance" --exclude "logs" --exclude "venv" \
        --exclude "app/static/uploads" \
        "$SOURCE_DIR/" "$APP_DIR/"
    ok "Código copiado para $APP_DIR."
    if [ -d "$SOURCE_DIR/.git" ] && confirm "Copiar também o histórico git (recomendado — permite 'git pull' em updates futuros)?" "s"; then
        rsync -a "$SOURCE_DIR/.git" "$APP_DIR/"
        ok "Histórico git copiado — dá para usar 'git pull' em $APP_DIR."
    fi
fi
mkdir -p "$APP_DIR/app/static/uploads" "$APP_DIR/instance" "$APP_DIR/logs"

# ---------------------------------------------------------------
# 4) Configuração do .env (guiada)
# ---------------------------------------------------------------
title "4/8 — Configurando variáveis de ambiente"
bash "$SCRIPT_DIR/configure-env.sh" "$APP_DIR/.env"

# ---------------------------------------------------------------
# 5) Ambiente virtual Python + dependências
# ---------------------------------------------------------------
title "5/8 — Instalando dependências Python"
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip wheel >/dev/null
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
ok "Dependências Python instaladas em $APP_DIR/venv."

if [ "$BUILD_FRONTEND" = "1" ]; then
    info "Construindo assets de front-end (Tailwind CSS)..."
    (cd "$APP_DIR" && npm ci && npm run build)
    ok "Assets de front-end gerados."
else
    warn "Build do Tailwind pulado — certifique-se de que app/static/css/tailwind.min.css já existe no pacote enviado."
fi

# ---------------------------------------------------------------
# 6) Banco de dados: migrações + admin
# ---------------------------------------------------------------
title "6/8 — Banco de dados"
set -a
# shellcheck disable=SC1091
source "$APP_DIR/.env"
set +a
export FLASK_APP=wsgi.py

(cd "$APP_DIR" && "$APP_DIR/venv/bin/flask" db upgrade)
ok "Migrações aplicadas."

(cd "$APP_DIR" && "$APP_DIR/venv/bin/flask" create-admin)
ok "Usuário administrador criado/atualizado (login: $ADMIN_EMAIL)."

if confirm "Popular o site com conteúdo de demonstração (serviços, galeria de exemplo)?" "n"; then
    (cd "$APP_DIR" && "$APP_DIR/venv/bin/flask" seed-demo)
    ok "Conteúdo de demonstração criado."
fi

# ---------------------------------------------------------------
# 7) Permissões
# ---------------------------------------------------------------
title "7/8 — Ajustando permissões"
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
chmod 600 "$APP_DIR/.env"
ok "Permissões ajustadas para o usuário '$APP_USER'."

# ---------------------------------------------------------------
# 8) systemd + Nginx
# ---------------------------------------------------------------
title "8/8 — Ativando os serviços"
sed -e "s#__APP_DIR__#${APP_DIR}#g" "$APP_DIR/deploy/midia-indoor.service" >/etc/systemd/system/midia-indoor.service
systemctl daemon-reload
systemctl enable --now midia-indoor
sleep 2
if systemctl is-active --quiet midia-indoor; then
    ok "Serviço midia-indoor rodando."
else
    err "O serviço midia-indoor não iniciou. Verifique: sudo journalctl -u midia-indoor -n 50"
fi

bash "$SCRIPT_DIR/setup-nginx.sh" "$APP_DIR"

if confirm "Configurar firewall básico (UFW: liberar SSH, HTTP e HTTPS)?" "s"; then
    command -v ufw >/dev/null 2>&1 || apt-get install -y ufw >/dev/null
    ufw allow OpenSSH >/dev/null || true
    ufw allow "Nginx Full" >/dev/null || true
    yes | ufw enable >/dev/null || true
    ok "UFW ativado (SSH + Nginx liberados)."
fi

SERVER_NAME_FINAL="$(grep -E '^SERVER_NAME=' "$APP_DIR/.env" | cut -d= -f2- | tr -d '"')"
USE_HTTPS_FINAL="$(grep -E '^USE_HTTPS=' "$APP_DIR/.env" | cut -d= -f2-)"
SSL_MODE_FINAL="$(grep -E '^SSL_MODE=' "$APP_DIR/.env" | cut -d= -f2- | tr -d '"')"
if [ "$USE_HTTPS_FINAL" = "1" ]; then
    URL="https://$SERVER_NAME_FINAL"
else
    URL="http://$SERVER_NAME_FINAL"
fi

echo
title "Instalação concluída! 🎉"
echo -e "  Site:        ${C_BOLD}$URL${C_RESET}"
echo -e "  Painel:      ${C_BOLD}$URL/login${C_RESET}"
echo -e "  Admin:       ${C_BOLD}$ADMIN_EMAIL${C_RESET}"
echo -e "  Diretório:   ${C_BOLD}$APP_DIR${C_RESET}"
if [ "$SSL_MODE_FINAL" = "selfsigned" ]; then
    echo
    warn "HTTPS ativo com certificado autoassinado (sem domínio ainda)."
    warn "O navegador vai avisar 'conexão não é privada' na primeira visita — clique em avançado/continuar. A conexão continua criptografada normalmente."
elif [ "$SSL_MODE_FINAL" = "custom" ]; then
    echo
    ok "HTTPS ativo com certificado comprado (CSR)."
    info "Sem renovação automática neste modo — rode 'sudo deploy/scripts/check-https.sh $APP_DIR' de vez em quando para acompanhar o vencimento."
fi
echo
echo "Comandos úteis:"
echo "  sudo systemctl status midia-indoor        # status da aplicação"
echo "  sudo journalctl -u midia-indoor -f         # logs em tempo real"
echo "  sudo bash deploy/scripts/update.sh          # publicar uma atualização"
echo "  sudo bash deploy/scripts/rollback.sh        # voltar para a versão anterior"
echo "  sudo bash deploy/scripts/configure-env.sh $APP_DIR/.env   # reconfigurar variáveis"
echo
