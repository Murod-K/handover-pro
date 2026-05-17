import os
import json
import logging
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db, storage

logger = logging.getLogger(__name__)

FIREBASE_CONFIG = {
    "type": "service_account",
    "project_id": "handover-pro-276a5",
    "private_key_id": os.environ.get("FIREBASE_PRIVATE_KEY_ID", ""),
    "private_key": os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
    "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL", ""),
    "client_id": os.environ.get("FIREBASE_CLIENT_ID", ""),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.environ.get("FIREBASE_CERT_URL", ""),
}

DATABASE_URL = "https://handover-pro-276a5-default-rtdb.europe-west1.firebasedatabase.app"
STORAGE_BUCKET = "handover-pro-276a5.firebasestorage.app"

_initialized = False

def init_firebase():
    global _initialized
    if _initialized:
        return
    try:
        cred = credentials.Certificate(FIREBASE_CONFIG)
        firebase_admin.initialize_app(cred, {
            "databaseURL": DATABASE_URL,
            "storageBucket": STORAGE_BUCKET,
        })
        _initialized = True
        logger.info("Firebase initialized")
    except Exception as e:
        logger.error(f"Firebase init error: {e}")
        raise

def get_db():
    if not _initialized:
        init_firebase()
    return db

# ─── USERS ──────────────────────────────────────────────────────────────────

def get_user_by_telegram_id(telegram_id: int) -> dict | None:
    ref = db.reference("users")
    users = ref.get() or {}
    for uid, user in users.items():
        if user.get("telegram_id") == telegram_id:
            return {**user, "id": uid}
    return None

def create_user(data: dict) -> str:
    ref = db.reference("users").push(data)
    return ref.key

def update_user(user_id: str, data: dict):
    db.reference(f"users/{user_id}").update(data)

def get_all_users() -> list:
    users = db.reference("users").get() or {}
    return [{**v, "id": k} for k, v in users.items()]

# ─── SHIFTS ─────────────────────────────────────────────────────────────────

def create_shift(data: dict) -> str:
    data["created_at"] = datetime.utcnow().isoformat()
    data["status"] = "open"
    ref = db.reference("shifts").push(data)
    return ref.key

def get_shift(shift_id: str) -> dict | None:
    data = db.reference(f"shifts/{shift_id}").get()
    if data:
        return {**data, "id": shift_id}
    return None

def update_shift(shift_id: str, data: dict):
    db.reference(f"shifts/{shift_id}").update(data)

def get_shifts_by_user(user_id: str, limit: int = 10) -> list:
    shifts = db.reference("shifts").get() or {}
    user_shifts = [
        {**v, "id": k}
        for k, v in shifts.items()
        if v.get("engineer_id") == user_id
    ]
    user_shifts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return user_shifts[:limit]

def get_open_shifts() -> list:
    shifts = db.reference("shifts").get() or {}
    return [
        {**v, "id": k}
        for k, v in shifts.items()
        if v.get("status") == "open"
    ]

def get_recent_shifts(limit: int = 20) -> list:
    shifts = db.reference("shifts").get() or {}
    all_shifts = [{**v, "id": k} for k, v in shifts.items()]
    all_shifts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return all_shifts[:limit]

# ─── PHOTOS ─────────────────────────────────────────────────────────────────

def add_photo_to_shift(shift_id: str, photo_url: str, construction_id: str = None):
    shift = get_shift(shift_id)
    if not shift:
        return
    photos = shift.get("photos", [])
    if len(photos) >= 10:
        return False
    photos.append({"url": photo_url, "construction_id": construction_id, "added_at": datetime.utcnow().isoformat()})
    update_shift(shift_id, {"photos": photos})
    return True

async def upload_photo_to_storage(file_bytes: bytes, filename: str) -> str:
    bucket = storage.bucket()
    blob = bucket.blob(f"shifts/{filename}")
    blob.upload_from_string(file_bytes, content_type="image/jpeg")
    blob.make_public()
    return blob.public_url

# ─── OBJECTS / SITES ─────────────────────────────────────────────────────────

def get_objects() -> list:
    objects = db.reference("objects").get() or {}
    return [{**v, "id": k} for k, v in objects.items()]

def get_object(obj_id: str) -> dict | None:
    data = db.reference(f"objects/{obj_id}").get()
    if data:
        return {**data, "id": obj_id}
    return None

# ─── PENDING STATES ──────────────────────────────────────────────────────────

def set_pending_state(telegram_id: int, state: dict):
    db.reference(f"pending_states/{telegram_id}").set(state)

def get_pending_state(telegram_id: int) -> dict | None:
    return db.reference(f"pending_states/{telegram_id}").get()

def clear_pending_state(telegram_id: int):
    db.reference(f"pending_states/{telegram_id}").delete()
