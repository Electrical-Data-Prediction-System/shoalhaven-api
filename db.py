from pymongo import MongoClient
from pymongo.server_api import ServerApi
from os import getenv
from dotenv import load_dotenv

load_dotenv()

uri = getenv("MONGODB_CONNECTION_STRING")

client = MongoClient(uri, server_api=ServerApi("1"))

try:
    client.admin.command("ping")
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
