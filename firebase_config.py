import json
import os

import firebase_admin
from firebase_admin import credentials, db


FIREBASE_CREDENTIAL_FILE = os.environ.get(
    "FIREBASE_CREDENTIAL_FILE",
    "serviceAccountKey.json",
)

FIREBASE_DATABASE_URL = os.environ.get(
    "FIREBASE_DATABASE_URL",
    "https://smart-log-70043-default-rtdb.asia-southeast1.firebasedatabase.app",
)


def initialize_firebase():
    """Initialize Firebase Admin once and return the database module."""
    if firebase_admin._apps:
        return db

    credential_json = os.environ.get("FIREBASE_CREDENTIAL_JSON")
    if credential_json:
        credential = credentials.Certificate(json.loads(credential_json))
    else:
        credential = credentials.Certificate(FIREBASE_CREDENTIAL_FILE)

    firebase_admin.initialize_app(
        credential,
        {"databaseURL": FIREBASE_DATABASE_URL},
    )
    print("[FIREBASE] Initialized successfully")
    return db


database = initialize_firebase()
