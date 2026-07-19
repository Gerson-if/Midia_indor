import importlib
import os

import pytest


def test_app_module_imports_without_database_url(monkeypatch):
    """
    Regressão: o módulo app.config não pode falhar ao ser importado
    apenas porque DATABASE_URL não está definida — isso só deve ser
    exigido quando ProductionConfig é de fato selecionado (validate()).
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import app.config as config_module

    importlib.reload(config_module)  # força reexecução do corpo do módulo
    assert config_module.ProductionConfig is not None


def test_production_config_validate_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "uma-chave-forte-qualquer")

    import app.config as config_module

    importlib.reload(config_module)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        config_module.ProductionConfig.validate()


def test_development_config_does_not_require_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from app import create_app

    app = create_app("development")
    assert app is not None
    assert app.config["SQLALCHEMY_DATABASE_URI"]
