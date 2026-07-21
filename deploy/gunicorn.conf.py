"""
Configuração do Gunicorn para produção.

Uso:
    gunicorn -c deploy/gunicorn.conf.py wsgi:app
"""
import multiprocessing
import os


def env_int(name, default):
    """Como os.environ.get(name, default) só usa o default quando a
    variável NÃO existe, uma linha tipo 'GUNICORN_WORKERS=' no .env
    (vazia de propósito, para usar o cálculo automático) fazia o
    int('') quebrar o Gunicorn logo na inicialização. Aqui, vazio
    também conta como "não definido"."""
    value = os.environ.get(name)
    return int(value) if value not in (None, "") else default


# ---- Bind ----
bind = os.environ.get("GUNICORN_BIND") or "127.0.0.1:8000"

# ---- Workers ----
# Padrão conservador (2 workers) — adequado para VPS pequenas (1-2 vCPU).
# Em servidores maiores, defina GUNICORN_WORKERS explicitamente
# (regra prática: 2 * núcleos + 1).
workers = env_int("GUNICORN_WORKERS", min(4, multiprocessing.cpu_count() * 2 + 1))
worker_class = "gthread"
threads = env_int("GUNICORN_THREADS", 2)
worker_tmp_dir = "/dev/shm"  # evita I/O em disco lento para heartbeat dos workers

# ---- Timeouts ----
timeout = env_int("GUNICORN_TIMEOUT", 30)
graceful_timeout = 30
keepalive = 5

# ---- Reciclagem de workers (evita vazamento de memória de longa duração) ----
max_requests = 1000
max_requests_jitter = 100

# ---- Logging ----
accesslog = "-"  # stdout (coletado pelo systemd/journald via `journalctl -u midia-indoor`)
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL") or "info"
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sus'
)

# ---- Processo ----
proc_name = "nexo-midia"
# preload_app=False (era True): com preload_app=True, o código da aplicação
# é importado UMA VEZ no processo mestre antes dos workers nascerem — por
# isso, um `kill -HUP` (o que `systemctl reload midia-indoor` faz, via
# ExecReload no midia-indoor.service) reinicia os workers, mas todos eles
# continuam com o MESMO código antigo já carregado em memória no mestre.
# Ou seja, "reload" não aplicava atualização nenhuma de código com
# preload_app=True — só um `restart` completo (parar tudo, depois subir de
# novo) fazia efeito, e isso significa uma janela real de indisponibilidade
# a cada deploy (a porta fica fechada entre o "stop" e o "start"), com
# usuários concorrentes recebendo erro de conexão bem no momento da
# atualização. Com preload_app=False, cada worker importa o código por
# conta própria, então um SIGHUP faz o mestre recarregar o código novo e
# trocar os workers antigos pelos novos GRADATIVAMENTE (o antigo termina
# as requisições em andamento antes de morrer) sem nunca fechar o socket
# de escuta — deploy sem downtime. O custo é perder o compartilhamento de
# memória copy-on-write entre workers, irrelevante frente a evitar quedas
# de serviço durante atualização.
preload_app = False

# ---- Segurança ----
limit_request_line = 4094
limit_request_fields = 100
