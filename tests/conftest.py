import importlib.util
from pathlib import Path

import pytest

import db
import dotenv


@pytest.fixture
def load_app(monkeypatch):
    def load(database=None, secret="test-secret-with-at-least-32-bytes"):
        monkeypatch.setattr(dotenv, "load_dotenv", lambda: None)
        monkeypatch.setattr(db, "connect_db", lambda: database)
        if secret is None:
            monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        else:
            monkeypatch.setenv("JWT_SECRET_KEY", secret)
        spec = importlib.util.spec_from_file_location(
            "app_under_test", Path(__file__).resolve().parents[1] / "app.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.app.config["TESTING"] = True
        return module

    return load
