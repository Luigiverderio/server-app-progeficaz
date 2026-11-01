from flask import Flask, jsonify, request
from flask_cors import CORS
from db import connect_db
import os
from datetime import timedelta
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token

load_dotenv()

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
CORS(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

db = connect_db()

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

    infos = collection_users.insert_one(new_user)

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)