#!/usr/bin/env bash
# =============================================================
# update.sh — publica uma atualização do Nexo Mídia.
#
# Modo git (recomendado — instalado com histórico git):
#   cd /opt/midia-indoor && sudo bash deploy/scripts/update.sh
#   -> faz "git pull" e segue o resto do processo.
#
# Modo zip (sem git): envie o novo código para a VPS e rode, de
# dentro da pasta extraída:
#   sudo bash deploy/scripts/update.sh /opt/midia-indoor
#   -> copia (rsync) o código novo por cima do que está em produção,
#      preservando venv/.env/uploads/logs/instance.
#
# Em qualquer um dos dois modos, o script:
#   1. faz backup rápido do banco e do .env
#   2. instala dependências novas/atualizadas
#   3. roda as migrações do banco (se falhar, para aqui sem tocar
#      em mais nada)
#   4. reinicia o serviço e confere /healthz
#   5. se /healthz não responder e o deploy for via git, desfaz o
#      "git pull" automaticamente (git reset --hard) e reinicia
#      com a versão anterior
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_root

APP_DIR="${1:-/opt/midia-indoor}"
[ -f "$APP_DIR/wsgi.py" ] || die "Não encontrei wsgi.py em $APP_DIR."
[ -f "$APP_DIR/.env" ] || die "$APP_DIR/.env não encontrado."

# ---------------------------------------------------------------
# Rede de segurança: se QUALQUER passo depois do "git pull" falhar
# (dependência Python que não instala, build do front-end que quebra,
# etc.), sem isso o script simplesmente parava no meio — deixando o
# código novo no disco só PARCIALMENTE aplicado, mas o serviço ainda
# rodando o processo antigo (com templates/estáticos já trocados no
# disco). É exatamente esse descompasso entre "código no disco" e
# "processo em memória" que costuma dar em página quebrada/comportamento
# estranho até alguém reiniciar o serviço manualmente. Agora, qualquer
# falha depois do pull desfaz o código automaticamente (git mode).
PREV_COMMIT=""
GIT_MODE=0
[ -d "$APP_DIR/.git" ] && GIT_MODE=1

on_update_error() {
    local line="$1"
    err "Falha inesperada em update.sh (linha $line)."
    if [ "$GIT_MODE" = "1" ] && [ -n "$PREV_COMMIT" ]; then
        err "Revertendo o código para o commit anterior ($PREV_COMMIT) para não deixar o servidor com código parcialmente atualizado..."
        git -C "$APP_DIR" reset --hard "$PREV_COMMIT" || true
        systemctl restart midia-indoor 2>/dev/null || true
        err "Revertido. O serviço foi reiniciado com a versão anterior."
    else
        err "Deploy via zip/rsync não tem rollback automático de código. O backup do banco/.env está em $APP_DIR/backups/."
        err "O serviço NÃO foi reiniciado — a versão antiga ainda deve estar rodando."
    fi
    err "Veja o erro real com: sudo journalctl -u midia-indoor -n 100"
    err "Corrija o problema indicado acima e rode o update.sh novamente."
}
trap 'on_update_error $LINENO' ERR

title "Atualização — Nexo Mídia ($APP_DIR)"

# ---------------------------------------------------------------
# 1) Backup rápido (banco + .env)
# ---------------------------------------------------------------
title "1/4 — Backup"
TS="$(date -u +%Y%m%d%H%M%S)"
BACKUP_DIR="$APP_DIR/backups"
mkdir -p "$BACKUP_DIR"
cp "$APP_DIR/.env" "$BACKUP_DIR/env-$TS.bak"

set -a
# shellcheck disable=SC1091
source "$APP_DIR/.env"
set +a

if [[ "${DATABASE_URL:-}" == sqlite:///* ]]; then
    DB_PATH="${DATABASE_URL#sqlite:///}"
    [[ "$DB_PATH" = /* ]] || DB_PATH="$APP_DIR/$DB_PATH"
    [ -f "$DB_PATH" ] && cp "$DB_PATH" "$BACKUP_DIR/db-$TS.sqlite3" && ok "Backup do SQLite salvo."
elif [[ "${DATABASE_URL:-}" == postgresql* ]] && command -v pg_dump >/dev/null 2>&1; then
    pg_dump "${DATABASE_URL/postgresql+psycopg2/postgresql}" >"$BACKUP_DIR/db-$TS.sql" 2>/dev/null \
        && ok "Backup do PostgreSQL salvo." \
        || warn "Não foi possível gerar o backup automático do PostgreSQL. Prosseguindo mesmo assim."
fi
ls -1t "$BACKUP_DIR"/db-* 2>/dev/null | tail -n +11 | xargs -r rm -f
ls -1t "$BACKUP_DIR"/env-* 2>/dev/null | tail -n +11 | xargs -r rm -f

# ---------------------------------------------------------------
# 2) Publicar o código novo
# ---------------------------------------------------------------
title "2/4 — Publicando o código novo"
if [ "$GIT_MODE" = "1" ]; then
    PREV_COMMIT="$(git -C "$APP_DIR" rev-parse HEAD)"
    git -C "$APP_DIR" pull --ff-only
    ok "git pull concluído (era $PREV_COMMIT)."
else
    SOURCE_DIR="$(pwd)"
    [ -f "$SOURCE_DIR/wsgi.py" ] || die "Rode este comando de dentro da pasta com o código novo, ex.: cd ~/midia-indoor-novo && sudo bash $APP_DIR/deploy/scripts/update.sh $APP_DIR"
    rsync -a \
        --exclude ".git" --exclude "__pycache__" --exclude "*.pyc" \
        --exclude "node_modules" --exclude ".env" \
        --exclude "instance" --exclude "logs" --exclude "venv" \
        --exclude "app/static/uploads" --exclude "backups" \
        "$SOURCE_DIR/" "$APP_DIR/"
    ok "Código copiado por cima de $APP_DIR (rsync)."
fi

# ---------------------------------------------------------------
# 3) Dependências + migrações
# ---------------------------------------------------------------
title "3/4 — Dependências e migrações"
"$APP_DIR/venv/bin/pip" install --upgrade pip wheel >/dev/null
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
ok "Dependências Python atualizadas."

if [ -f "$APP_DIR/package.json" ] && command -v npm >/dev/null 2>&1; then
    if (cd "$APP_DIR" && npm ci && npm run build); then
        ok "Assets de front-end reconstruídos."
    else
        err "Falha ao instalar/compilar os assets de front-end (npm ci / npm run build)."
        err "Causas comuns: sem acesso à internet/registro npm nesta VPS, ou uma dependência incompatível com a versão do Node instalada."
        exit 1
    fi
fi

export FLASK_APP=wsgi.py
if ! (cd "$APP_DIR" && "$APP_DIR/venv/bin/flask" db upgrade); then
    trap - ERR
    err "Falha ao aplicar as migrações. O serviço NÃO foi reiniciado."
    if [ "$GIT_MODE" = "1" ] && [ -n "$PREV_COMMIT" ]; then
        err "Revertendo o código para o commit anterior ($PREV_COMMIT), já que as migrações não passaram (evita rodar código novo contra o schema antigo)..."
        git -C "$APP_DIR" reset --hard "$PREV_COMMIT" || true
    fi
    err "Corrija o problema e rode o update.sh novamente. Backup do banco está em $BACKUP_DIR."
    exit 1
fi
ok "Migrações aplicadas."
chown -R midia-indoor:midia-indoor "$APP_DIR"

# ---------------------------------------------------------------
# 4) Aplicar a nova versão e checar /healthz
# ---------------------------------------------------------------
title "4/4 — Aplicando a nova versão e verificando"
trap - ERR   # a partir daqui o script já tem seu próprio tratamento específico de falha/rollback abaixo

# Antes usávamos sempre "systemctl restart", que para o processo por
# completo antes de iniciar o novo — o socket fica fechado nesse meio
# tempo, então qualquer usuário acessando o site bem nesse instante do
# deploy recebia erro de conexão. Com preload_app=False (gunicorn.conf.py)
# e o ExecReload configurado no serviço systemd, "reload" (SIGHUP) troca
# o código gradualmente: os workers antigos terminam as requisições em
# andamento e só então são substituídos pelos novos, sem nunca fechar a
# porta de escuta — atualização sem downtime perceptível. Se o serviço
# ainda não estiver rodando (primeira publicação), cai para "start".
if systemctl is-active --quiet midia-indoor; then
    systemctl reload midia-indoor
else
    systemctl start midia-indoor
fi

BIND="$(grep -E '^GUNICORN_BIND=' "$APP_DIR/.env" | cut -d= -f2- || true)"
BIND="${BIND:-127.0.0.1:8000}"

HEALTHY=0
for i in $(seq 1 15); do
    sleep 1
    curl -fsS "http://$BIND/healthz" >/dev/null 2>&1 && { HEALTHY=1; break; }
done

if [ "$HEALTHY" = "1" ]; then
    ok "Atualização concluída — nova versão no ar e respondendo em /healthz."
    exit 0
fi

err "A nova versão não respondeu em /healthz."
if [ -n "$PREV_COMMIT" ]; then
    err "Revertendo automaticamente (git reset --hard $PREV_COMMIT)..."
    git -C "$APP_DIR" reset --hard "$PREV_COMMIT"
    "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" >/dev/null
    (cd "$APP_DIR" && "$APP_DIR/venv/bin/flask" db upgrade) || true
    systemctl restart midia-indoor
    err "Rollback concluído — versão anterior ($PREV_COMMIT) ativa novamente."
else
    err "Deploy via zip/rsync não tem rollback automático. Restaure o backup se necessário: $BACKUP_DIR"
fi
err "Verifique os logs antes de tentar de novo: sudo journalctl -u midia-indoor -n 100"
exit 1
