"""Testes HTTP com banco falso: nenhuma conexão com o Atlas é criada."""

import os
from unittest.mock import MagicMock, patch

import pytest


# app.py conecta ao banco durante o import. O patch precisa existir antes dele:
# o nome db.connect_db é importado por app.py e já aponta para o falso.
with (
    patch("dotenv.load_dotenv"),
    patch.dict(os.environ, {"JWT_SECRET_KEY": "test-secret-with-at-least-32-bytes"}),
    patch("db.connect_db", return_value=MagicMock()),
):
    from app import app


@pytest.fixture
def database():
    return MagicMock()


@pytest.fixture
def client(database):
    # Após o import, as rotas usam app.db, que recebe um falso novo por teste.
    with patch("app.db", database), patch.dict(app.config, {"TESTING": True}):
        with app.test_client() as test_client:
            yield test_client


def test_health(client):
    # Given: aplicação em modo de teste com banco falso disponível.
    # When: o cliente consulta a saúde do servidor.
    response = client.get("/health")

    # Then: o servidor responde com sucesso.
    assert response.status_code == 200
    assert response.json == {"status": "ok"}
