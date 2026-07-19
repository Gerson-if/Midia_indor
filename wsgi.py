"""
Ponto de entrada WSGI usado pelo Gunicorn em produção:

    gunicorn -c deploy/gunicorn.conf.py wsgi:app

Em desenvolvimento, use `flask run` (lê FLASK_APP=wsgi.py do .env)
ou simplesmente `python wsgi.py`.
"""
import os

from app import create_app

app = create_app(os.environ.get("FLASK_ENV", "production"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
