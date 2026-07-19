#!/bin/sh
# =============================================================
# Entrypoint do container: aplica migrations automaticamente
# antes de iniciar o Gunicorn, evitando subir a aplicação com
# o schema do banco desatualizado.
# =============================================================
set -e

echo "Aguardando banco de dados ficar disponível..."
python - <<'PYEOF'
import os
import time
import sys

from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit(0)

for attempt in range(30):
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Banco de dados disponível.")
        break
    except Exception as exc:  # noqa: BLE001
        print(f"Tentativa {attempt + 1}/30: banco indisponível ({exc}). Aguardando...")
        time.sleep(2)
else:
    print("Não foi possível conectar ao banco de dados a tempo.")
    sys.exit(1)
PYEOF

echo "Aplicando migrations..."
flask db upgrade

echo "Iniciando aplicação..."
exec "$@"
