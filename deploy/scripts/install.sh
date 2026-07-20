#!/usr/bin/env bash
# =============================================================
# install.sh — instalação guiada do Nexo Mídia em uma VPS Ubuntu,
# SEM Docker: Python + venv + Gunicorn + systemd + Nginx.
#
# Como usar (na VPS, dentro da pasta do projeto já extraída):
#   sudo bash deploy/scripts/install.sh
#
# O script é idempotente: pode ser executado de novo com segurança
# (por exemplo, para reinstalar após corrigir algum problema).
#
# Estrutura criada em /opt/midia-indoor:
#   releases/<timestamp>/   -> código de cada versão publicada
#   current -> symlink para a release ativa
#   shared/.env             -> variáveis de ambiente (preservado)
#   shared/venv             -> ambiente virtual Python (preservado)
#   shared/uploads          -> mídias enviadas pelo painel (preservado)
#   shared/instance         -> banco SQLite, se usado (preservado)
#   shared/logs             -> logs da aplicação (preservado)
#   shared/backups          -> backups automáticos gerados no update.sh
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root

# Diretório onde o instalador foi extraído (raiz do projeto/código-fonte)
SOURCE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
[ -f "$SOURCE_DIR/wsgi.py" ] || die "Não encontrei wsgi.py em $SOURCE_DIR — rode este script de dentro do projeto extraído."

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
title "1/9 — Instalando pacotes do sistema (apt)"
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
title "2/9 — Usuário de sistema"
if ! id "$APP_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin --create-home "$APP_USER"
    ok "Usuário de sistema '$APP_USER' criado."
else
    ok "Usuário de sistema '$APP_USER' já existe."
fi

# ---------------------------------------------------------------
# 3) Estrutura de diretórios + cópia do código (releases)
# ---------------------------------------------------------------
title "3/9 — Publicando o código em $APP_DIR"
RELEASE_ID="$(date -u +%Y%m%d%H%M%S)"
RELEASE_DIR="$APP_DIR/releases/$RELEASE_ID"
mkdir -p "$APP_DIR/releases" "$APP_DIR/shared/venv" "$APP_DIR/shared/uploads" \
    "$APP_DIR/shared/instance" "$APP_DIR/shared/logs" "$APP_DIR/shared/backups"
mkdir -p "$RELEASE_DIR"

rsync -a \
    --exclude ".git" --exclude ".github" \
    --exclude "__pycache__" --exclude "*.pyc" \
    --exclude "node_modules" --exclude ".env" \
    --exclude "instance" --exclude "logs" \
    --exclude "app/static/uploads" \
    "$SOURCE_DIR/" "$RELEASE_DIR/"

ln -sfn "$RELEASE_DIR" "$APP_DIR/current"
ok "Código publicado em $RELEASE_DIR (current -> $RELEASE_DIR)"

# ---------------------------------------------------------------
# 4) Configuração do .env (guiada)
# ---------------------------------------------------------------
title "4/9 — Configurando variáveis de ambiente"
bash "$SCRIPT_DIR/configure-env.sh" "$APP_DIR/shared/.env"

# ---------------------------------------------------------------
# 5) Links simbólicos para dados persistentes
# ---------------------------------------------------------------
title "5/9 — Ligando pastas persistentes (uploads, logs, instance)"
rm -rf "$APP_DIR/current/app/static/uploads"
ln -sfn "$APP_DIR/shared/uploads" "$APP_DIR/current/app/static/uploads"
rm -rf "$APP_DIR/current/logs"
ln -sfn "$APP_DIR/shared/logs" "$APP_DIR/current/logs"
rm -rf "$APP_DIR/current/instance"
ln -sfn "$APP_DIR/shared/instance" "$APP_DIR/current/instance"
ok "Links prontos — uploads/logs/banco sqlite sobrevivem a futuras atualizações."

# ---------------------------------------------------------------
# 6) Ambiente virtual Python + dependências
# ---------------------------------------------------------------
title "6/9 — Instalando dependências Python"
if [ ! -x "$APP_DIR/shared/venv/bin/python" ]; then
    python3 -m venv "$APP_DIR/shared/venv"
fi
"$APP_DIR/shared/venv/bin/pip" install --upgrade pip wheel >/dev/null
"$APP_DIR/shared/venv/bin/pip" install -r "$APP_DIR/current/requirements.txt"
ok "Dependências Python instaladas em shared/venv."

if [ "$BUILD_FRONTEND" = "1" ]; then
    info "Construindo assets de front-end (Tailwind CSS)..."
    (cd "$APP_DIR/current" && npm ci && npm run build)
    ok "Assets de front-end gerados."
else
    warn "Build do Tailwind pulado — certifique-se de que app/static/css/tailwind.min.css já existe no pacote enviado."
fi

# ---------------------------------------------------------------
# 7) Banco de dados: migrações + admin
# ---------------------------------------------------------------
title "7/9 — Banco de dados"
set -a
# shellcheck disable=SC1091
source "$APP_DIR/shared/.env"
set +a
export FLASK_APP=wsgi.py

(cd "$APP_DIR/current" && "$APP_DIR/shared/venv/bin/flask" db upgrade)
ok "Migrações aplicadas."

(cd "$APP_DIR/current" && "$APP_DIR/shared/venv/bin/flask" create-admin)
ok "Usuário administrador criado/atualizado (login: $ADMIN_EMAIL)."

if confirm "Popular o site com conteúdo de demonstração (serviços, galeria de exemplo)?" "n"; then
    (cd "$APP_DIR/current" && "$APP_DIR/shared/venv/bin/flask" seed-demo)
    ok "Conteúdo de demonstração criado."
fi

# ---------------------------------------------------------------
# 8) Permissões
# ---------------------------------------------------------------
title "8/9 — Ajustando permissões"
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
chmod 600 "$APP_DIR/shared/.env"
ok "Permissões ajustadas para o usuário '$APP_USER'."

# ---------------------------------------------------------------
# 9) systemd + Nginx
# ---------------------------------------------------------------
title "9/9 — Ativando os serviços"
cp "$APP_DIR/current/deploy/midia-indoor.service" /etc/systemd/system/midia-indoor.service
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
    if command -v ufw >/dev/null 2>&1; then
        ufw allow OpenSSH >/dev/null || true
        ufw allow "Nginx Full" >/dev/null || true
        yes | ufw enable >/dev/null || true
        ok "UFW ativado (SSH + Nginx liberados)."
    else
        apt-get install -y ufw >/dev/null
        ufw allow OpenSSH >/dev/null || true
        ufw allow "Nginx Full" >/dev/null || true
        yes | ufw enable >/dev/null || true
        ok "UFW instalado e ativado (SSH + Nginx liberados)."
    fi
fi

SERVER_NAME_FINAL="$(grep -E '^SERVER_NAME=' "$APP_DIR/shared/.env" | cut -d= -f2-)"
USE_HTTPS_FINAL="$(grep -E '^USE_HTTPS=' "$APP_DIR/shared/.env" | cut -d= -f2-)"
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
echo
echo "Comandos úteis:"
echo "  sudo systemctl status midia-indoor        # status da aplicação"
echo "  sudo journalctl -u midia-indoor -f         # logs em tempo real"
echo "  sudo bash deploy/scripts/update.sh          # publicar uma atualização com segurança"
echo "  sudo bash deploy/scripts/rollback.sh        # voltar para a versão anterior"
echo "  sudo bash deploy/scripts/configure-env.sh $APP_DIR/shared/.env   # reconfigurar variáveis"
echo
