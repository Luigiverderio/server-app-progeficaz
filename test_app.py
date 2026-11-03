"""Testes HTTP com banco falso: nenhuma conexão com o Atlas é criada."""

import os
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId
from flask_jwt_extended import create_access_token, decode_token


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


@pytest.fixture
def auth_headers():
    with app.app_context():
        token = create_access_token(identity="usuario-logado")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def favorita():
    return {
        "_id": ObjectId(),
        "user_id": "usuario-logado",
        "nome": "Casa para faculdade",
        "origem": "Av. Paulista, 1578, São Paulo",
        "destino": "Rua Quatá, 300, São Paulo",
        "ultima_duracao_min": 30.0,
    }


@pytest.mark.parametrize("method,path", [
    ("post", "/favoritas"),
    ("get", "/favoritas"),
    ("put", "/favoritas/507f1f77bcf86cd799439011"),
    ("delete", "/favoritas/507f1f77bcf86cd799439011"),
])
def test_favoritas_exige_token(client, database, method, path):
    # Given: uma requisição sem token de autenticação.
    # When: o cliente tenta acessar uma das rotas de favoritas.
    response = getattr(client, method)(path)

    # Then: o acesso é negado antes de consultar o banco.
    assert response.status_code == 401
    database.__getitem__.assert_not_called()


def test_cria_favorita_com_dono_do_token(client, database, auth_headers, favorita):
    # Given: dados válidos e uma tentativa de informar outro dono pelo corpo.
    body = {key: value for key, value in favorita.items() if key != "_id"}
    body["user_id"] = "outro-usuario"
    database["favoritas"].insert_one.return_value.inserted_id = favorita["_id"]

    # When: o cliente autenticado salva a favorita.
    response = client.post("/favoritas", json=body, headers=auth_headers)

    # Then: a favorita é criada e pertence ao usuário do token.
    assert response.status_code == 201
    assert response.json == {"id": str(favorita["_id"])}
    saved = database["favoritas"].insert_one.call_args.args[0]
    assert saved == dict(body, user_id="usuario-logado")


def test_lista_apenas_favoritas_do_usuario(client, database, auth_headers, favorita):
    # Given: favoritas de dois usuários diferentes no banco falso.
    documents = [favorita, dict(favorita, _id=ObjectId(), user_id="outro-usuario")]
    database["favoritas"].find.side_effect = lambda query: [
        doc for doc in documents if all(doc.get(key) == value for key, value in query.items())
    ]

    # When: o cliente solicita suas favoritas.
    response = client.get("/favoritas", headers=auth_headers)

    # Then: somente o registro do usuário autenticado aparece, sem expor o dono.
    assert response.status_code == 200
    assert response.json == {
        "total": 1,
        "favoritas": [{
            "id": str(favorita["_id"]),
            "nome": favorita["nome"],
            "origem": favorita["origem"],
            "destino": favorita["destino"],
            "ultima_duracao_min": favorita["ultima_duracao_min"],
        }],
    }


def test_lista_favoritas_vazia(client, database, auth_headers):
    # Given: o usuário ainda não possui favoritas.
    database["favoritas"].find.return_value = []

    # When: o cliente consulta a lista.
    response = client.get("/favoritas", headers=auth_headers)

    # Then: recebe uma lista vazia com status de sucesso.
    assert response.status_code == 200
    assert response.json == {"total": 0, "favoritas": []}


@pytest.mark.parametrize("duration", [15.0, 30.0])
def test_atualiza_duracao_da_favorita(client, database, auth_headers, favorita, duration):
    # Given: uma favorita do usuário, inclusive quando a duração não muda.
    database["favoritas"].find_one_and_update.return_value = dict(
        favorita, ultima_duracao_min=duration,
    )

    # When: o cliente atualiza a duração e tenta alterar campos não permitidos.
    response = client.put(f"/favoritas/{favorita['_id']}", json={
        "ultima_duracao_min": duration, "nome": "Outro nome", "user_id": "outro-usuario",
    }, headers=auth_headers)

    # Then: só a duração é atualizada, com filtro de propriedade.
    assert response.status_code == 200
    assert response.json["id"] == str(favorita["_id"])
    assert response.json["ultima_duracao_min"] == duration
    assert response.json["nome"] == favorita["nome"]
    args = database["favoritas"].find_one_and_update.call_args.args
    assert args == (
        {"_id": favorita["_id"], "user_id": "usuario-logado"},
        {"$set": {"ultima_duracao_min": duration}},
    )


def test_apaga_favorita_do_usuario(client, database, auth_headers, favorita):
    # Given: uma favorita pertencente ao usuário autenticado.
    database["favoritas"].delete_one.return_value.deleted_count = 1

    # When: o cliente solicita a exclusão.
    response = client.delete(f"/favoritas/{favorita['_id']}", headers=auth_headers)

    # Then: a exclusão é filtrada pelo dono e a resposta não tem corpo.
    assert response.status_code == 204
    assert response.data == b""
    database["favoritas"].delete_one.assert_called_once_with({
        "_id": favorita["_id"], "user_id": "usuario-logado",
    })


@pytest.mark.parametrize("method", ["put", "delete"])
@pytest.mark.parametrize("scenario", ["id-invalido", "inexistente", "outro-usuario"])
def test_favorita_nao_encontrada(client, database, auth_headers, favorita, method, scenario):
    # Given: ID inválido, favorita inexistente ou favorita de outro usuário.
    documents = []
    if scenario == "outro-usuario":
        documents.append(dict(favorita, user_id="outro-usuario"))

    def find_owned(query, *args, **kwargs):
        return next((doc for doc in documents
                     if all(doc.get(key) == value for key, value in query.items())), None)

    database["favoritas"].find_one_and_update.side_effect = find_owned
    database["favoritas"].delete_one.side_effect = lambda query: MagicMock(
        deleted_count=int(find_owned(query) is not None),
    )
    identifier = "invalido" if scenario == "id-invalido" else str(favorita["_id"])

    # When: o cliente tenta atualizar ou apagar a favorita.
    response = getattr(client, method)(f"/favoritas/{identifier}",
                                      json={"ultima_duracao_min": 10}, headers=auth_headers)

    # Then: os três casos retornam 404 sem revelar dados de outro usuário.
    assert response.status_code == 404
    assert response.json == {"erro": "Favorita não encontrada"}
