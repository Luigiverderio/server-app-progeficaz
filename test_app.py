"""Testes HTTP com banco falso: nenhuma conexão com o Atlas é criada."""

import os
from unittest.mock import MagicMock, patch

import pytest
import requests
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


@pytest.fixture
def rota_http():
    import app as app_module

    # Cada teste começa sem cache e simula somente a fronteira HTTP externa.
    with (
        patch.object(app_module, "_geocode_cache", {}),
        patch.object(app_module, "_geocode_last_request", None),
        patch("app.time.sleep"),
        patch("requests.get") as get,
    ):
        yield get


@pytest.fixture
def resposta_http():
    def response(payload, status=200):
        result = MagicMock(spec=requests.Response)
        result.status_code = status
        result.json.return_value = payload
        if status >= 400:
            result.raise_for_status.side_effect = requests.exceptions.HTTPError()
        return result
    return response


@pytest.fixture
def enderecos():
    return {"origem": "Av. Paulista, 1578, São Paulo", "destino": "Rua Quatá, 300, São Paulo"}


@pytest.fixture
def geocodes(resposta_http):
    return [
        resposta_http([{"lat": "-23.5615", "lon": "-46.6560"}]),
        resposta_http([{"lat": "-23.5983", "lon": "-46.6765"}]),
    ]


def test_rota_exige_token(client, rota_http, enderecos):
    # Given: endereços válidos, mas nenhum token.
    # When: o cliente tenta calcular a rota.
    response = client.post("/rota", json=enderecos)

    # Then: a autenticação impede o acesso antes das APIs externas.
    assert response.status_code == 401
    rota_http.assert_not_called()


@pytest.mark.parametrize("body", [
    {}, {"origem": "A"}, {"destino": "B"},
    {"origem": " ", "destino": "B"}, {"origem": 123, "destino": "B"},
])
def test_rota_rejeita_entrada_invalida(client, auth_headers, rota_http, body):
    # Given: campos obrigatórios ausentes ou inválidos.
    # When: o usuário autenticado solicita uma rota.
    response = client.post("/rota", json=body, headers=auth_headers)

    # Then: nenhuma consulta externa é feita e a entrada é rejeitada.
    assert response.status_code == 400
    rota_http.assert_not_called()


def test_rota_retorna_trajeto_simulado(client, auth_headers, rota_http, resposta_http, geocodes, enderecos):
    # Given: duas respostas do Nominatim e uma do OSRM, nessa ordem.
    rota_http.side_effect = geocodes + [resposta_http({
        "code": "Ok",
        "routes": [{
            "duration": 600,
            "distance": 1250,
            "geometry": {"coordinates": [[-46.6560, -23.5615], [-46.6765, -23.5983]]},
        }],
    })]

    # When: o usuário calcula o trajeto com as APIs simuladas.
    response = client.post("/rota", json=enderecos, headers=auth_headers)

    # Then: recebe coordenadas em lat/lng, minutos e quilômetros.
    assert response.status_code == 200
    assert response.json == {
        "duracao_min": 10.0,
        "distancia_km": 1.25,
        "coordenadas": [[-23.5615, -46.6560], [-23.5983, -46.6765]],
        "origem": {"lat": -23.5615, "lng": -46.6560},
        "destino": {"lat": -23.5983, "lng": -46.6765},
    }
    assert rota_http.call_count == 3
    calls = rota_http.call_args_list
    assert calls[0].kwargs["params"]["q"] == enderecos["origem"]
    assert calls[1].kwargs["params"]["q"] == enderecos["destino"]
    assert "/routed-foot/" in calls[2].args[0]
    assert "-46.656,-23.5615;-46.6765,-23.5983" in calls[2].args[0]


@pytest.mark.parametrize("missing", ["origem", "destino"])
def test_rota_endereco_nao_encontrado(client, auth_headers, rota_http, resposta_http, geocodes, enderecos, missing):
    # Given: o Nominatim não encontra um dos endereços.
    rota_http.side_effect = ([] if missing == "origem" else geocodes[:1]) + [resposta_http([])]

    # When: o usuário solicita a rota.
    response = client.post("/rota", json=enderecos, headers=auth_headers)

    # Then: retorna 404 sem consultar o OSRM.
    assert response.status_code == 404
    assert missing in response.json["erro"]
    assert rota_http.call_count == (1 if missing == "origem" else 2)


@pytest.mark.parametrize("service", ["nominatim", "osrm"])
@pytest.mark.parametrize("failure", ["http", "timeout", "conexao", "json"])
def test_rota_falha_externa(client, auth_headers, rota_http, resposta_http, geocodes, enderecos, service, failure):
    # Given: uma API externa falha, sempre sem conexão real.
    if failure == "http":
        failed = resposta_http({}, status=503)
    elif failure == "json":
        failed = resposta_http(None)
        failed.json.side_effect = requests.exceptions.JSONDecodeError("JSON inválido", "", 0)
    elif failure == "timeout":
        failed = requests.exceptions.Timeout("Tempo esgotado")
    else:
        failed = requests.exceptions.ConnectionError("Sem internet")
    rota_http.side_effect = ([] if service == "nominatim" else geocodes) + [failed]

    # When: o usuário solicita a rota durante a indisponibilidade.
    response = client.post("/rota", json=enderecos, headers=auth_headers)

    # Then: o servidor responde 502 sem propagar a exceção.
    assert response.status_code == 502
    assert rota_http.call_count == (1 if service == "nominatim" else 3)
