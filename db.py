import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

load_dotenv()

def connect_db():
    try:
        client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=5000)
        db = client[os.getenv("DB_NAME")]
        db.command("ping")
    except PyMongoError:
        return None

    return db