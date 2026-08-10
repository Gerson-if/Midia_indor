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

# Se algo falhar, mostra em qual linha/comando foi, em vez de só
# "erro" genérico — acelera bastante o diagnóstico em VPS remota.
trap 'err "Instalação interrompida (linha $LINENO: \"$BASH_COMMAND\"). Nada foi desfeito automaticamente — corrija o problema apontado acima e rode este script de novo (ele é idempotente)."' ERR

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

# ---------------------------------------------------------------
# 0) Checagens prévias — pegar problemas ANTES de mexer no sistema,
#    em vez de descobrir no meio da instalação (mais rápido de
#    corrigir e não deixa a VPS pela metade).
# ---------------------------------------------------------------
title "0/9 — Checagens prévias do ambiente"

if [ -f /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    if [ "${ID:-}" = "ubuntu" ]; then
        case "${VERSION_ID:-}" in
            22.04|24.04) ok "Ubuntu ${VERSION_ID} — suportado." ;;
            *) warn "Ubuntu ${VERSION_ID:-desconhecido} não foi testado (testado em 22.04/24.04) — pode funcionar, mas fique atento a erros de pacote." ;;
        esac
    else
        warn "Distribuição '${ID:-desconhecida}' não é Ubuntu — este instalador foi feito para Ubuntu 22.04/24.04 e pode falhar em outras distros."
    fi
fi

FREE_KB="$(df -Pk "$SOURCE_DIR" | awk 'NR==2 {print $4}')"
if [ -n "$FREE_KB" ] && [ "$FREE_KB" -lt 1048576 ]; then
    warn "Menos de 1 GB livre em disco — a instalação de dependências pode falhar por falta de espaço."
fi

if ! retry 3 3 curl -fsS --max-time 5 -o /dev/null https://pypi.org; then
    die "Sem conexão com a internet (falhei ao acessar pypi.org). Confira a rede/DNS da VPS antes de continuar."
fi
ok "Conectividade com a internet OK."

for p in 80 443; do
    if port_in_use "$p"; then
        warn "A porta $p já está em uso por outro processo (Apache/Nginx padrão da distro?). O Caddy pode falhar ao subir mais adiante. Veja: sudo ss -ltnp | grep :$p"
    fi
done

ask "Em qual diretório instalar a aplicação?" "/opt/midia-indoor" APP_DIR

# ---------------------------------------------------------------
# 1) Pacotes do sistema
# ---------------------------------------------------------------
title "1/9 — Instalando pacotes do sistema (apt)"
export DEBIAN_FRONTEND=noninteractive
retry 3 5 apt-get update -y
retry 3 5 apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip python3-dev \
    build-essential libpq-dev libmagic1 libjpeg-dev zlib1g-dev \
    git curl rsync ca-certificates gnupg debian-keyring debian-archive-keyring apt-transport-https

if confirm "Este projeto usará PostgreSQL (recomendado em produção)?" "s"; then
    retry 3 5 apt-get install -y --no-install-recommends postgresql postgresql-contrib
    systemctl enable --now postgresql
    for _ in 1 2 3 4 5; do systemctl is-active --quiet postgresql && break; sleep 1; done
    systemctl is-active --quiet postgresql || die "PostgreSQL não iniciou. Verifique: sudo journalctl -u postgresql -n 50"
fi

if confirm "Instalar Redis (recomendado para rate limiting em produção)?" "s"; then
    retry 3 5 apt-get install -y --no-install-recommends redis-server
    systemctl enable --now redis-server
    for _ in 1 2 3 4 5; do systemctl is-active --quiet redis-server && break; sleep 1; done
    systemctl is-active --quiet redis-server || die "Redis não iniciou. Verifique: sudo journalctl -u redis-server -n 50"
fi

info "HTTPS é automático: o Caddy (instalado a seguir) emite e renova certificados Let's Encrypt sozinho, sob demanda, para qualquer domínio que você apontar para esta VPS — inclusive páginas novas cadastradas depois pelo painel do super admin, sem precisar rodar nada aqui de novo."

BUILD_FRONTEND=0
if confirm "Construir os assets de front-end (Tailwind CSS) agora? (requer Node.js/npm)" "s"; then
    if ! command -v npm >/dev/null 2>&1; then
        info "Node.js não encontrado — instalando (NodeSource, LTS)..."
        retry 3 5 bash -c "curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - >/dev/null"
        retry 3 5 apt-get install -y --no-install-recommends nodejs
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
# 3) Publicar o código em APP_DIR (pasta única, sem releases)
# ---------------------------------------------------------------
title "3/9 — Publicando o código em $APP_DIR"
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
title "4/9 — Configurando variáveis de ambiente"
bash "$SCRIPT_DIR/configure-env.sh" "$APP_DIR/.env"

# ---------------------------------------------------------------
# 5) Ambiente virtual Python + dependências
# ---------------------------------------------------------------
title "5/9 — Instalando dependências Python"
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
    python3 -m venv "$APP_DIR/venv"
fi
retry 3 5 "$APP_DIR/venv/bin/pip" install --upgrade pip wheel >/dev/null
retry 3 5 "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
ok "Dependências Python instaladas em $APP_DIR/venv."

if [ "$BUILD_FRONTEND" = "1" ]; then
    info "Construindo assets de front-end (Tailwind CSS)..."
    (cd "$APP_DIR" && retry 3 5 npm ci && npm run build)
    [ -f "$APP_DIR/app/static/css/tailwind.min.css" ] || die "Build do Tailwind não gerou app/static/css/tailwind.min.css — confira a saída de 'npm run build' acima."
    ok "Assets de front-end gerados."
elif [ ! -f "$APP_DIR/app/static/css/tailwind.min.css" ]; then
    warn "Build do Tailwind pulado e app/static/css/tailwind.min.css não existe — o site vai subir SEM estilo até você rodar 'npm ci && npm run build' em $APP_DIR."
else
    ok "Build do Tailwind pulado — app/static/css/tailwind.min.css já existe no pacote enviado."
fi

# ---------------------------------------------------------------
# 6) Banco de dados: migrações + admin
# ---------------------------------------------------------------
title "6/9 — Banco de dados"
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
title "7/9 — Ajustando permissões"
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
chmod 600 "$APP_DIR/.env"
ok "Permissões ajustadas para o usuário '$APP_USER'."

# ---------------------------------------------------------------
# 7.1) Atalho global "nexo" — painel de controle interativo, sem
#      precisar decorar caminho/nome de cada script depois.
# ---------------------------------------------------------------
cat >/usr/local/bin/nexo <<NEXOEOF
#!/usr/bin/env bash
exec bash "$APP_DIR/deploy/scripts/menu.sh" "$APP_DIR" "\$@"
NEXOEOF
chmod +x /usr/local/bin/nexo
ok "Atalho 'nexo' instalado — a partir de agora, 'sudo nexo' abre o painel de controle (backup, restauração, migração, atualização, status etc)."

# ---------------------------------------------------------------
# 8) systemd + Caddy (HTTPS automático, qualquer domínio)
# ---------------------------------------------------------------
title "8/9 — Ativando os serviços"
sed -e "s#__APP_DIR__#${APP_DIR}#g" "$APP_DIR/deploy/midia-indoor.service" >/etc/systemd/system/midia-indoor.service
systemctl daemon-reload
systemctl enable --now midia-indoor

# systemctl is-active só confirma que o processo não morreu — não que
# a aplicação de fato responde. Testamos o /healthz local (via Gunicorn
# direto, antes do Caddy entrar em cena) para pegar erros de app
# (import quebrado, .env errado, banco inacessível) aqui, com uma
# mensagem clara, em vez de um 502 confuso no navegador depois.
GUNICORN_BIND_VAL="$(grep -E '^GUNICORN_BIND=' "$APP_DIR/.env" | cut -d= -f2- | tr -d '"')"
HEALTH_URL="http://${GUNICORN_BIND_VAL:-127.0.0.1:8000}/healthz"
if systemctl is-active --quiet midia-indoor && wait_for_http "$HEALTH_URL" 30; then
    ok "Serviço midia-indoor rodando e respondendo em $HEALTH_URL."
else
    err "O serviço midia-indoor não respondeu em $HEALTH_URL dentro de 30s."
    err "Verifique: sudo journalctl -u midia-indoor -n 80"
    die "Corrija o erro acima e rode 'sudo systemctl restart midia-indoor' antes de continuar (ou rode install.sh de novo — ele é idempotente)."
fi

bash "$SCRIPT_DIR/setup-caddy.sh" "$APP_DIR"

if confirm "Configurar firewall básico (UFW: liberar SSH, HTTP e HTTPS)?" "s"; then
    command -v ufw >/dev/null 2>&1 || retry 3 5 apt-get install -y ufw >/dev/null
    ufw allow OpenSSH >/dev/null || true
    ufw allow 80/tcp >/dev/null || true
    ufw allow 443/tcp >/dev/null || true
    yes | ufw enable >/dev/null || true
    ok "UFW ativado (SSH + 80/443 liberados)."
fi

DOMAIN_FINAL="$(grep -E '^SERVER_NAME=' "$APP_DIR/.env" | cut -d= -f2- | tr -d '"')"
if [ -n "$DOMAIN_FINAL" ]; then
    URL="https://$DOMAIN_FINAL"
else
    URL="http://$(curl -fsS -4 ifconfig.me 2>/dev/null || echo "<IP-desta-VPS>")"
fi
PG_DB_NAME_FINAL="$(grep -E '^PG_DB_NAME=' "$APP_DIR/.env" | cut -d= -f2- | tr -d '"')"

# Resumo final também gravado em arquivo (só root consegue ler) —
# senhas geradas automaticamente somem da tela ao rolar o terminal;
# ficam preservadas aqui além de já estarem no .env.
CREDS_FILE="/root/midia-indoor-instalacao-$(date +%Y%m%d-%H%M%S).txt"
umask 077
cat >"$CREDS_FILE" <<CREDSEOF
Nexo Mídia — resumo da instalação em $(date -u +"%Y-%m-%dT%H:%M:%SZ")

Site:      $URL
Painel:    $URL/login
Diretório: $APP_DIR

Administrador:
  E-mail: $ADMIN_EMAIL
  Senha:  $ADMIN_PASSWORD

$( [ -n "$PG_DB_NAME_FINAL" ] && echo "Banco de dados (.env em $APP_DIR/.env tem a senha completa):
  Nome: $PG_DB_NAME_FINAL" )

Este arquivo NÃO é necessário para o funcionamento do sistema — é só
uma cópia de leitura rápida das credenciais geradas nesta instalação.
Depois de anotar em um cofre de senhas, apague-o com:
  sudo shred -u $CREDS_FILE
CREDSEOF
ok "Resumo de credenciais salvo em $CREDS_FILE (permissão 600, só root lê)."

echo
title "Instalação concluída! 🎉"
echo -e "  Site:        ${C_BOLD}$URL${C_RESET}"
echo -e "  Painel:      ${C_BOLD}$URL/login${C_RESET}"
echo -e "  Admin:       ${C_BOLD}$ADMIN_EMAIL${C_RESET}"
echo -e "  Diretório:   ${C_BOLD}$APP_DIR${C_RESET}"
echo -e "  Credenciais: ${C_BOLD}$CREDS_FILE${C_RESET} ${C_YELLOW}(apague depois de anotar)${C_RESET}"
if [ -n "$DOMAIN_FINAL" ]; then
    echo
    info "HTTPS já foi validado nesta instalação (Caddy + Let's Encrypt, automático a cada domínio novo)."
else
    echo
    warn "Nenhum domínio configurado ainda: o site está acessível só por HTTP/IP. Para ativar HTTPS, cadastre um domínio pelo painel do super admin (/superadmin) e aponte o DNS dele para o IP desta VPS, ou rode 'sudo bash deploy/scripts/configure-env.sh $APP_DIR/.env' de novo."
fi
echo
echo "Painel do super admin (cria/gerencia/bloqueia páginas de clientes):"
echo "  $URL/superadmin/login"
echo "  (crie o primeiro acesso com: sudo -u midia-indoor bash -c 'cd $APP_DIR && SUPERADMIN_EMAIL=... SUPERADMIN_PASSWORD=... venv/bin/flask create-superadmin')"
echo
echo "Cada instalação gera SECRET_KEY, senha do banco e senha do admin únicas — nada disso é compartilhado entre VPS/clientes diferentes."
echo
title "Painel de controle: sudo nexo"
echo "A partir de agora, o comando abaixo abre um menu interativo com tudo:"
echo "atualizar, backup completo, restaurar, migrar para outro servidor,"
echo "reverter versão, status/logs/reiniciar, firewall, reconfigurar .env:"
echo
echo -e "  ${C_BOLD}sudo nexo${C_RESET}"
echo
echo "Atalhos diretos (sem passar pelo menu), pra quem preferir/automatizar:"
echo "  sudo bash deploy/scripts/update.sh           # publicar uma atualização"
echo "  sudo bash deploy/scripts/backup.sh           # backup completo (banco + uploads)"
echo "  sudo bash deploy/scripts/restore.sh          # restaurar um backup"
echo "  sudo bash deploy/scripts/migrate.sh          # assistente de migração p/ servidor novo"
echo "  sudo bash deploy/scripts/rollback.sh         # voltar para a versão anterior de código"
echo "  sudo systemctl status midia-indoor           # status da aplicação"
echo "  sudo systemctl status caddy                  # status do proxy/HTTPS"
echo "  sudo journalctl -u midia-indoor -f           # logs em tempo real"
echo "  curl -s $HEALTH_URL                          # healthcheck local direto (sem passar pelo Caddy)"
echo
