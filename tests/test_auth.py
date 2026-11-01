from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from types import SimpleNamespace

import pytest
from pymongo.errors import DuplicateKeyError


class Users:
    """In-memory collection that enforces only indexes requested by the app."""

    def __init__(self):
        self.documents = []
        self.unique_email = False
        self.barrier = None
        self.lock = Lock()

    def create_index(self, field, unique=False):
        assert field == "email"
        self.unique_email = unique

    def find_one(self, query):
        with self.lock:
            found = next(
                (d for d in self.documents if d["email"] == query["email"]), None
            )
        if self.barrier:
            self.barrier.wait(timeout=10)
        return found

    def insert_one(self, document):
        with self.lock:
            if self.unique_email and any(
                d["email"] == document["email"] for d in self.documents
            ):
                raise DuplicateKeyError("duplicate email")
            document["_id"] = str(len(self.documents) + 1)
            self.documents.append(document)
            return SimpleNamespace(inserted_id=document["_id"])


class Database:
    def __init__(self):
        self.users = Users()

    def __getitem__(self, key):
        assert key == "users"
        return self.users


@pytest.fixture
def auth(load_app):
    database = Database()
    return load_app(database), database


def register(module, password="valid-password", email="user@example.com"):
    with module.app.test_client() as client:
        return client.post(
            "/auth/register",
            json={"name": "User", "email": email, "password": password},
        )


@pytest.mark.parametrize("password", ["x" * 73, "á" * 37])
def test_register_rejects_password_over_72_utf8_bytes(auth, password):
    module, database = auth
    response = register(module, password=password)
    assert response.status_code == 400
    assert response.is_json
    assert database.users.documents == []


@pytest.mark.parametrize("password", ["x" * 72, "á" * 36])
def test_register_accepts_72_utf8_bytes_and_hashes_password(auth, password):
    module, database = auth
    response = register(module, password=password)
    assert response.status_code == 201
    stored = database.users.documents[0]["password"]
    assert stored != password
    assert module.bcrypt.check_password_hash(stored, password)


def test_email_index_is_unique(auth):
    _, database = auth
    assert database.users.unique_email


def test_concurrent_registrations_allow_only_one_email(auth):
    module, database = auth
    database.users.barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: register(module), range(2)))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert len(database.users.documents) == 1


def test_repeated_email_returns_conflict(auth):
    module, _ = auth
    assert register(module).status_code == 201
    assert register(module).status_code == 409


def test_register_unavailable_database(load_app):
    module = load_app()
    assert register(module).status_code == 503


@pytest.mark.parametrize("password", ["x" * 73, "á" * 37])
@pytest.mark.parametrize("existing", [True, False])
def test_login_long_password_has_generic_error(auth, password, existing):
    module, _ = auth
    if existing:
        assert register(module).status_code == 201
    with module.app.test_client() as client:
        response = client.post(
            "/auth/login", json={"email": "user@example.com", "password": password}
        )
    assert response.status_code == 401
    assert response.json == {"erro": "E-mail ou senha inválidos"}


@pytest.mark.parametrize("password", ["valid-password", "x" * 72, "á" * 36])
def test_register_then_login_returns_valid_token(auth, password):
    from flask_jwt_extended import decode_token

    module, _ = auth
    registered = register(module, password=password)
    with module.app.test_client() as client:
        response = client.post(
            "/auth/login", json={"email": "user@example.com", "password": password}
        )
    assert response.status_code == 200
    assert response.json["name"] == "User"
    with module.app.app_context():
        claims = decode_token(response.json["token"])
    assert claims["sub"] == registered.json["id"]
    assert claims["exp"] - claims["iat"] == 3600


def test_login_invalid_credentials_have_same_error(auth):
    module, _ = auth
    assert register(module).status_code == 201
    with module.app.test_client() as client:
        wrong_password = client.post(
            "/auth/login", json={"email": "user@example.com", "password": "wrong"}
        )
        unknown_email = client.post(
            "/auth/login", json={"email": "unknown@example.com", "password": "wrong"}
        )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json == unknown_email.json


@pytest.mark.parametrize("route", ["register", "login"])
@pytest.mark.parametrize(
    "body", [None, [], {}, {"email": 123, "password": "valid-password"},
             {"name": "User", "email": "   ", "password": "valid-password"}]
)
def test_auth_invalid_input(auth, route, body):
    module, _ = auth
    with module.app.test_client() as client:
        response = client.post("/auth/" + route, json=body)
    assert response.status_code == 400


def test_login_unavailable_database(load_app):
    module = load_app()
    with module.app.test_client() as client:
        response = client.post(
            "/auth/login", json={"email": "user@example.com", "password": "valid-password"}
        )
    assert response.status_code == 503
