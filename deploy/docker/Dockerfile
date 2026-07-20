# =============================================================
# Dockerfile — Nexo Mídia (Flask + Gunicorn)
# Build multi-stage: reduz o tamanho final da imagem.
# =============================================================
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Dependências de sistema necessárias em runtime:
# - libmagic1: validação real do tipo de arquivo em uploads
# - ffmpeg: otimização/recodificação dos vídeos enviados no Hero
# - libpq5: driver PostgreSQL (psycopg2-binary já embute libpq, mas
#   mantemos por segurança em algumas distros slim)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Stage de dependências (cacheável) ----
FROM base AS deps
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# ---- Stage final ----
FROM base AS final

RUN addgroup --system app && adduser --system --ingroup app app

COPY --from=deps /root/.local /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH

COPY . .

RUN mkdir -p /app/instance /app/logs /app/app/static/uploads \
    && chown -R app:app /app \
    && chmod +x /app/deploy/docker/entrypoint.sh

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["/app/deploy/docker/entrypoint.sh"]
CMD ["gunicorn", "-c", "deploy/gunicorn.conf.py", "wsgi:app"]
