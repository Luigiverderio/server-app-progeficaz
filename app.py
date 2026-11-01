from flask import Flask, jsonify
from flask_cors import CORS
from db import connect_db
import os
from datetime import timedelta
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager

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

@app.route("/health", methods=["GET"])
def health():
    if db is None:
        return jsonify({"erro": "Banco de dados indisponível"}), 503

    db.command("ping")
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
