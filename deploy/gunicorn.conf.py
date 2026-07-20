"""
Configuração do Gunicorn para produção.

Uso:
    gunicorn -c deploy/gunicorn.conf.py wsgi:app
"""
import multiprocessing
import os

# ---- Bind ----
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")

# ---- Workers ----
# Padrão conservador (2 workers) — adequado para VPS pequenas (1-2 vCPU).
# Em servidores maiores, defina GUNICORN_WORKERS explicitamente
# (regra prática: 2 * núcleos + 1).
workers = int(os.environ.get("GUNICORN_WORKERS", min(4, multiprocessing.cpu_count() * 2 + 1)))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", 2))
worker_tmp_dir = "/dev/shm"  # evita I/O em disco lento para heartbeat dos workers

# ---- Timeouts ----
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 30))
graceful_timeout = 30
keepalive = 5

# ---- Reciclagem de workers (evita vazamento de memória de longa duração) ----
max_requests = 1000
max_requests_jitter = 100

# ---- Logging ----
accesslog = "-"  # stdout (coletado pelo systemd/journald via `journalctl -u midia-indoor`)
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sus'
)

# ---- Processo ----
proc_name = "nexo-midia"
preload_app = True  # compartilha memória entre workers (copy-on-write)

# ---- Segurança ----
limit_request_line = 4094
limit_request_fields = 100
