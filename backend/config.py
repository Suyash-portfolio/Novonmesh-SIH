import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(32).hex())

    _db_url = os.environ.get("DATABASE_URL", "")
    if not _db_url:
        _db_path = str(BASE_DIR / "database" / "navonmesh.db")
        os.makedirs(os.path.dirname(_db_path), exist_ok=True)
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{_db_path}"
    else:
        if _db_url.startswith("postgres://"):
            _db_url = _db_url.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = _db_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    _upload = os.environ.get("UPLOAD_DIR", str(BASE_DIR / "uploads"))
    os.makedirs(_upload, exist_ok=True)
    UPLOAD_FOLDER = _upload

    _output = os.environ.get("OUTPUT_DIR", str(BASE_DIR / "outputs"))
    os.makedirs(_output, exist_ok=True)
    OUTPUT_DIR = _output

    _evidence = os.environ.get("EVIDENCE_DIR", str(BASE_DIR / "evidence"))
    os.makedirs(_evidence, exist_ok=True)
    EVIDENCE_DIR = _evidence

    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", 2048)) * 1024 * 1024
    REDIS_URL = os.environ.get("REDIS_URL", "")
    DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"

    VEHICLE_MODEL_PATH = os.environ.get("VEHICLE_MODEL_PATH", str(BASE_DIR / "yolov8n.pt"))
    VEHICLE_MODEL_URL = os.environ.get("VEHICLE_MODEL_URL", "")
    PLATE_MODEL_PATH = os.environ.get("PLATE_MODEL_PATH", str(BASE_DIR / "models" / "license_plate.pt"))
    PLATE_MODEL_URL = os.environ.get("PLATE_MODEL_URL", "")
    REID_MODEL_PATH = os.environ.get("REID_MODEL_PATH", str(BASE_DIR / "osnet_x1_0.pth"))

    YOLO_VEHICLE_MODEL = VEHICLE_MODEL_PATH
    YOLO_PLATE_MODEL = PLATE_MODEL_PATH

    CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.4"))
    OCR_CONFIDENCE_THRESHOLD = float(os.environ.get("OCR_CONFIDENCE_THRESHOLD", "0.5"))
    FRAME_SKIP = int(os.environ.get("FRAME_SKIP", "3"))
    OCR_INTERVAL = int(os.environ.get("OCR_INTERVAL", "1"))
