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
# Regra prática: 2 * núcleos + 1. Ajustável via variável de ambiente.
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", 4))
worker_tmp_dir = "/dev/shm"  # evita I/O em disco lento para heartbeat dos workers

# ---- Timeouts ----
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 30))
graceful_timeout = 30
keepalive = 5

# ---- Reciclagem de workers (evita vazamento de memória de longa duração) ----
max_requests = 1000
max_requests_jitter = 100

# ---- Logging ----
accesslog = "-"  # stdout (coletado pelo systemd/journald ou docker logs)
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
