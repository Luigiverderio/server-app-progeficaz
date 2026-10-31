from flask import Flask, jsonify
from flask_cors import CORS
from db import connect_db

app = Flask(__name__)
CORS(app)
db = connect_db()

@app.route("/health", methods=["GET"])
def health():
    if db is None:
        return jsonify({"erro": "Banco de dados indisponível"}), 503

    db.command("ping")
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)