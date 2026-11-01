from flask import Flask, jsonify, request
from flask_cors import CORS
from db import connect_db
import os
import time
from threading import Lock
import requests
from datetime import timedelta
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required
from pymongo.errors import DuplicateKeyError
from routing import buscar_rota

load_dotenv()

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
if not app.config["JWT_SECRET_KEY"] or not app.config["JWT_SECRET_KEY"].strip():
    raise RuntimeError("JWT_SECRET_KEY deve estar configurada e não pode ser vazia")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
CORS(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

db = connect_db()
if db is not None:
    db["users"].create_index("email", unique=True)

_geocode_lock = Lock()
_geocode_cache = {}
_geocode_last_request = None


def geocode(address):
    """Retorna (latitude, longitude) em graus, None quando
    não encontra o endereço e lança RuntimeError em falhas do serviço.

    Limita consultas a uma por segundo e guarda até 128 endereços por processo.
    """
    global _geocode_last_request
    if not isinstance(address, str) or not address.strip():
        return None
    address = address.strip()

    with _geocode_lock:
        if address in _geocode_cache:
            return _geocode_cache[address]

        if _geocode_last_request is not None:
            time.sleep(max(0, 1 - (time.monotonic() - _geocode_last_request)))
        _geocode_last_request = time.monotonic()

        try:
            response = requests.get(
                os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"),
                params={"q": address, "format": "json", "limit": 1},
                headers={"User-Agent": "server-app-progeficaz/1.0 (https://github.com/Luigiverderio/server-app-progeficaz)"},
                timeout=5,
            )
            if response.status_code != 200:
                raise RuntimeError("Falha no serviço de geocodificação")
            results = response.json()
            if not isinstance(results, list):
                raise RuntimeError("Falha no serviço de geocodificação")
            coordinates = None
            if results:
                latitude = float(results[0]["lat"])
                longitude = float(results[0]["lon"])
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    raise RuntimeError("Falha no serviço de geocodificação")
                coordinates = (latitude, longitude)
        except (requests.exceptions.RequestException, ValueError, KeyError, TypeError):
            raise RuntimeError("Falha no serviço de geocodificação")

        if len(_geocode_cache) >= 128:
            _geocode_cache.pop(next(iter(_geocode_cache)))
        _geocode_cache[address] = coordinates
        return coordinates


@app.route("/health", methods=["GET"])
def health():
    if db is None:
        return jsonify({"erro": "Banco de dados indisponível"}), 503

    db.command("ping")
    return jsonify({"status": "ok"}), 200

@app.route("/auth/register", methods=["POST"])
def register():
    body = request.get_json(silent=True)
    if not type(body) is dict:
        return jsonify({"erro": "Entrada inválida."}), 400
    if not body.get("name") or not body.get("email") or not body.get("password"):
        return jsonify({"erro": "Entrada inválida."}), 400
    if not type(body["name"]) is str or not type(body["email"]) is str or not type(body["password"]) is str:
        return jsonify({"erro": "Entrada inválida."}), 400

    body["name"] = body["name"].strip()
    body["email"] = body["email"].strip()

    if "" in [body["name"], body["email"], body["password"].strip()]:
        return jsonify({"erro": "Entrada inválida."}), 400

    if len(body["password"].encode("utf-8")) > 72:
        return jsonify({"erro": "A senha deve ter no máximo 72 bytes em UTF-8."}), 400

    if db is None:
        return jsonify({"erro": "Banco de dados indisponível"}), 503

    collection_users = db["users"]

    if collection_users.find_one({ "email": body["email"]}):
        return jsonify({"erro": "E-mail já cadastrado"}), 409

    new_user = {
        "name": body["name"],
        "email": body["email"],
        "password": bcrypt.generate_password_hash(body["password"]).decode("utf-8")
    }

    try:
        infos = collection_users.insert_one(new_user)
    except DuplicateKeyError:
        return jsonify({"erro": "E-mail já cadastrado"}), 409

    return jsonify({"id": str(infos.inserted_id)}), 201

@app.route("/auth/login", methods=["POST"])
def login():
    body = request.get_json(silent=True)
    if not type(body) is dict:
        return jsonify({"erro": "Entrada inválida."}), 400
    if not body.get("email") or not body.get("password"):
        return jsonify({"erro": "Entrada inválida."}), 400
    if not type(body["email"]) is str or not type(body["password"]) is str:
        return jsonify({"erro": "Entrada inválida."}), 400

    body["email"] = body["email"].strip()

    if "" in [body["email"], body["password"].strip()]:
        return jsonify({"erro": "Entrada inválida."}), 400

    if len(body["password"].encode("utf-8")) > 72:
        return jsonify({"erro": "E-mail ou senha inválidos"}), 401

    if db is None:
        return jsonify({"erro": "Banco de dados indisponível"}), 503

    collection_users = db["users"]
    user = collection_users.find_one({"email": body["email"]})

    if not user:
        return jsonify({"erro": "E-mail ou senha inválidos"}), 401

    if not bcrypt.check_password_hash(user["password"], body["password"]):
        return jsonify({"erro": "E-mail ou senha inválidos"}), 401

    token = create_access_token(identity=str(user["_id"]))

    return jsonify({"token": token, "name": user["name"]}), 200

@app.route("/rota", methods=["POST"])
@jwt_required()
def rota():
    body = request.get_json(silent=True)

    if not type(body) is dict:
        return jsonify({"erro": "Entrada inválida."}), 400
    if not body.get("origem") or not body.get("destino"):
        return jsonify({"erro": "Entrada inválida."}), 400
    if not type(body["origem"]) is str or not type(body["destino"]) is str:
        return jsonify({"erro": "Entrada inválida."}), 400

    body["origem"] = body["origem"].strip()
    body["destino"] = body["destino"].strip()

    if "" in [body["origem"], body["destino"]]:
        return jsonify({"erro": "Entrada inválida."}), 400

    try:
        geocode_origem = geocode(body["origem"])

        if not geocode_origem:
            return jsonify({"erro": "Não foi possível encontrar a origem."}), 404

        geocode_destino = geocode(body["destino"])

        if not geocode_destino:
            return jsonify({"erro": "Não foi possível encontrar o destino."}), 404
    except RuntimeError:
        return jsonify({"erro": "Falha no serviço de geocodificação"}), 502

    origem = {"lat": geocode_origem[0], "lng": geocode_origem[1]}
    destino = {"lat": geocode_destino[0], "lng": geocode_destino[1]}

    rota_encontrada = buscar_rota(origem, destino)

    if not rota_encontrada:
        return jsonify({"erro": "Falha no serviço de rotas."}), 502

    return jsonify({
        "duracao_min": rota_encontrada["duracao_min"],
        "distancia_km": rota_encontrada["distancia_km"],
        "coordenadas": rota_encontrada["coordenadas"],
        "origem": origem,
        "destino": destino}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
