from flask import Flask, jsonify
from flask_cors import CORS
from db import db

app = Flask(__name__)
CORS(app)

@app.route("/health", methods=["GET"])
def health():
    db.command("ping")
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)