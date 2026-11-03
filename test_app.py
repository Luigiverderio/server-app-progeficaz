"""Testes HTTP com banco falso: nenhuma conexão com o Atlas é criada."""

import os
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId
from flask_jwt_extended import decode_token


# app.py conecta ao banco durante o import. O patch precisa existir antes dele:
# o nome db.connect_db é importado por app.py e já aponta para o falso.
with (
    patch("dotenv.load_dotenv"),
    patch.dict(os.environ, {"JWT_SECRET_KEY": "test-secret-with-at-least-32-bytes"}),
    patch("db.connect_db", return_value=MagicMock()),
):
    from app import app, bcrypt


@pytest.fixture
def database():
    database = MagicMock()
    collections = {"users": MagicMock(), "favoritas": MagicMock()}
    database.__getitem__.side_effect = collections.__getitem__
    collections["users"].find_one.return_value = None
    collections["users"].insert_one.return_value.inserted_id = ObjectId()
    return database


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


@pytest.fixture
def cadastro():
    return {"name": "Ana", "email": "ana@example.com", "password": "senha-valida"}


def test_register_cria_usuario(client, database, cadastro):
    # Given: um cadastro válido e um e-mail ainda não utilizado.
    # When: o cliente solicita o cadastro.
    response = client.post("/auth/register", json=cadastro)

    # Then: o usuário é criado e sua senha é armazenada como hash.
    assert response.status_code == 201
    assert ObjectId.is_valid(response.json["id"])
    saved = database["users"].insert_one.call_args.args[0]
    assert saved["name"] == cadastro["name"]
    assert saved["email"] == cadastro["email"]
    assert saved["password"] != cadastro["password"]
    assert bcrypt.check_password_hash(saved["password"], cadastro["password"])


@pytest.mark.parametrize("field", ["name", "email", "password"])
@pytest.mark.parametrize("value", [None, "", "   ", 123])
def test_register_rejeita_campo_invalido(client, database, cadastro, field, value):
    # Given: um campo obrigatório ausente ou inválido.
    cadastro.pop(field)
    if value is not None:
        cadastro[field] = value

    # When: o cliente tenta se cadastrar.
    response = client.post("/auth/register", json=cadastro)

    # Then: a entrada é rejeitada sem inserir um usuário.
    assert response.status_code == 400
    database["users"].insert_one.assert_not_called()


def test_register_rejeita_email_duplicado(client, database, cadastro):
    # Given: o banco falso já contém o e-mail solicitado.
    database["users"].find_one.return_value = {"email": cadastro["email"]}

    # When: outro cadastro usa o mesmo e-mail.
    response = client.post("/auth/register", json=cadastro)

    # Then: o servidor informa o conflito sem criar outro usuário.
    assert response.status_code == 409
    database["users"].insert_one.assert_not_called()


def test_login_retorna_token_valido(client, database, cadastro):
    # Given: um usuário com senha armazenada como hash no banco falso.
    user_id = ObjectId()
    database["users"].find_one.return_value = {
        "_id": user_id,
        "name": cadastro["name"],
        "email": cadastro["email"],
        "password": bcrypt.generate_password_hash(cadastro["password"]).decode("utf-8"),
    }

    # When: o cliente envia as credenciais corretas.
    response = client.post("/auth/login", json={
        "email": cadastro["email"], "password": cadastro["password"],
    })

    # Then: recebe um token válido que identifica esse usuário.
    assert response.status_code == 200
    assert response.json["name"] == cadastro["name"]
    with app.app_context():
        claims = decode_token(response.json["token"])
    assert claims["sub"] == str(user_id)


@pytest.mark.parametrize("existing_user", [False, True])
def test_login_rejeita_credenciais_incorretas(client, database, cadastro, existing_user):
    # Given: o usuário não existe ou a senha enviada não corresponde ao hash.
    if existing_user:
        database["users"].find_one.return_value = {
            "password": bcrypt.generate_password_hash(cadastro["password"]).decode("utf-8"),
        }

    # When: o cliente tenta entrar com credenciais inválidas.
    response = client.post("/auth/login", json={
        "email": cadastro["email"], "password": "senha-incorreta",
    })

    # Then: ambos os casos retornam a mesma resposta sem token.
    assert response.status_code == 401
    assert response.json == {"erro": "E-mail ou senha inválidos"}


@pytest.mark.parametrize("field", ["email", "password"])
def test_login_rejeita_campo_ausente(client, cadastro, field):
    # Given: um corpo de login sem um campo obrigatório.
    body = {"email": cadastro["email"], "password": cadastro["password"]}
    body.pop(field)

    # When: o cliente tenta entrar.
    response = client.post("/auth/login", json=body)

    # Then: o servidor informa entrada inválida.
    assert response.status_code == 400
