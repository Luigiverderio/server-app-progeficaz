import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

load_dotenv()

def connect_db():
    uri = os.getenv("MONGO_URI", "").strip()
    database_name = os.getenv("DB_NAME", "").strip()
    if not uri or not database_name:
        return None

    client = None
    try:
        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=5000,
        )
        db = client[database_name]
        db.command("ping")
    except PyMongoError:
        if client is not None:
            client.close()
        return None

    return db
