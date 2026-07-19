import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from pythonjsonlogger import jsonlogger


def configure_logging(app):
    """
    Configura logging da aplicação:
    - Em produção: JSON estruturado (fácil de indexar em ELK/Datadog/etc.)
    - Arquivo rotativo em LOG_DIR/app.log (10MB x 5 backups)
    - Também escreve em stdout quando LOG_TO_STDOUT=1 (útil em containers)
    """
    log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    log_dir = app.config.get("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)

    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(pathname)s %(lineno)d"
    )
    plain_formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    )

    handlers = []

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"), maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(formatter if app.config.get("ENV") == "production" else plain_formatter)
    file_handler.setLevel(log_level)
    handlers.append(file_handler)

    if app.config.get("LOG_TO_STDOUT", True):
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter if app.config.get("ENV") == "production" else plain_formatter)
        stream_handler.setLevel(log_level)
        handlers.append(stream_handler)

    app.logger.handlers = []
    for handler in handlers:
        app.logger.addHandler(handler)
    app.logger.setLevel(log_level)
    app.logger.propagate = False

    # Reduz verbosidade de bibliotecas de terceiros
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.WARNING if app.config.get("ENV") != "development" else logging.WARNING
    )

    app.logger.info("Logging configurado (nível=%s, ambiente=%s)", app.config.get("LOG_LEVEL"), app.config.get("ENV"))
