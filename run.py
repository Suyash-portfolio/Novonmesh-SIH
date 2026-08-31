#!/usr/bin/env python3
"""
NAVONMESH Sightlines — Auto-Bootstrapping Entry Point
====================================================
Just run:  python run.py
"""

import os
import sys
import subprocess
import importlib
import warnings
import threading

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="urllib3")
warnings.filterwarnings("ignore", message="RequestsDependency")
warnings.filterwarnings("ignore", category=UserWarning)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)

REQUIRED_DIRS = [
    "uploads", "outputs", "models", "database", "data", "logs", "evidence",
    "backend", "backend/routes", "backend/services", "backend/models",
    "templates", "static", "static/css", "static/js",
]

DEPS_CORE = [
    ("flask",              "flask",                 ">=3.0",     True),
    ("flask_sqlalchemy",   "Flask-SQLAlchemy",      ">=3.1",     True),
    ("flask_migrate",      "Flask-Migrate",         ">=4.0",     True),
    ("flask_socketio",     "Flask-SocketIO",        ">=5.3",     True),
    ("sqlalchemy",         "SQLAlchemy",             ">=2.0",     True),
    ("dotenv",             "python-dotenv",          ">=1.0",     True),
    ("werkzeug",           "Werkzeug",               ">=2.0",     True),
    ("numpy",              "numpy",                  ">=1.24",    True),
    ("cv2",                "opencv-python-headless", ">=4.8",     True),
    ("PIL",                "Pillow",                 ">=10.0",    True),
]

DEPS_AI_REQUIRED = [
    ("ultralytics",        "ultralytics",            ">=8.0",     True),
    ("torch",              "torch",                  ">=2.0",     True),
    ("torchvision",        "torchvision",            ">=0.15",    True),
]

DEPS_AI_OPTIONAL = [
    ("paddleocr",          "paddleocr",              ">=2.7",     False),
]

DEPS_OPTIONAL = [
    ("redis",              "redis",                  ">=5.0",     False),
    ("eventlet",           "eventlet",               ">=0.36",    False),
    ("sklearn",            "scikit-learn",           ">=1.3",     False),
    ("scipy",              "scipy",                  ">=1.11",    False),
]


class C:
    OK = "\033[92m"
    WARN = "\033[93m"
    FAIL = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    END = "\033[0m"


def st(msg, state="ok"):
    tags = {
        "ok":   f"  {C.OK}[OK]{C.END}     {msg}",
        "warn": f"  {C.WARN}[WARN]{C.END}   {msg}",
        "fail": f"  {C.FAIL}[FAIL]{C.END}   {msg}",
        "info": f"  {C.BOLD}[..]{C.END}     {msg}",
        "skip": f"  {C.DIM}[--]{C.END}     {msg}",
    }
    print(tags.get(state, tags["info"]), flush=True)


def try_import(name):
    try:
        return True, importlib.import_module(name)
    except Exception:
        return False, None


def pip_install(pkg, ver=""):
    spec = f"{pkg}{ver}" if ver else pkg
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "--disable-pip-version-check", "--timeout", "60",
             "--retries", "2", spec],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=300,
        )
        return result.returncode == 0
    except Exception:
        return False


def pip_install_async(pkg, ver=""):
    spec = f"{pkg}{ver}" if ver else pkg

    def _install():
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet",
                 "--disable-pip-version-check", "--timeout", "60",
                 "--retries", "2", "--no-cache-dir", spec],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=600,
            )
        except Exception:
            pass

    t = threading.Thread(target=_install, daemon=True)
    t.start()
    return t


def ensure_deps(deps, label="Dependencies"):
    missing = []
    for imp_name, pip_name, ver, required in deps:
        ok, _ = try_import(imp_name)
        if ok:
            st(f"Import {pip_name}")
        else:
            st(f"Installing {pip_name}...", "info")
            installed = pip_install(pip_name, ver)
            if installed:
                ok2, _ = try_import(imp_name)
                if ok2:
                    st(f"Import {pip_name}")
                    continue
            if required:
                st(f"{pip_name} is REQUIRED — cannot continue", "fail")
                missing.append(pip_name)
            else:
                st(f"{pip_name} — optional, skipping", "skip")
    return len(missing) == 0


def ensure_model(model_path, download_fn, label):
    if os.path.exists(model_path):
        st(f"{label}: {os.path.basename(model_path)}")
        return True
    st(f"Downloading {label}...", "info")
    try:
        download_fn(model_path)
        if os.path.exists(model_path) and os.path.getsize(model_path) > 1000:
            st(f"{label}: {os.path.basename(model_path)}")
            return True
        else:
            st(f"{label} download produced empty/missing file", "warn")
            return False
    except Exception as e:
        st(f"{label} download failed: {e}", "warn")
        return False


def download_yolo(path):
    from ultralytics import YOLO
    YOLO("yolov8n.pt")


def main():
    print(flush=True)
    print(f"{C.BOLD}{'=' * 56}{C.END}", flush=True)
    print(f"{C.BOLD}  NAVONMESH Sightlines — SIH26127{C.END}", flush=True)
    print(f"{C.BOLD}  City-Wide AI Engine for Multi-Camera ANPR{C.END}", flush=True)
    print(f"{C.BOLD}{'=' * 56}{C.END}", flush=True)
    print(flush=True)

    print(f"{C.BOLD}[1/7] Python Environment{C.END}", flush=True)
    v = sys.version_info
    st(f"Python {v.major}.{v.minor}.{v.micro} ({sys.executable})")
    if v.major < 3 or v.minor < 9:
        st("Python 3.9+ required", "fail")
        sys.exit(1)
    print(flush=True)

    print(f"{C.BOLD}[2/7] Core Dependencies{C.END}", flush=True)
    if not ensure_deps(DEPS_CORE, "Core"):
        st("Cannot continue without core packages", "fail")
        sys.exit(1)
    print(flush=True)

    print(f"{C.BOLD}[3/7] AI Dependencies{C.END}", flush=True)
    bg_threads = []
    still_missing = []
    for imp_name, pip_name, ver, required in DEPS_AI_REQUIRED:
        ok, _ = try_import(imp_name)
        if ok:
            st(f"Import {pip_name}")
        else:
            st(f"Installing {pip_name}...", "info")
            t = pip_install_async(pip_name, ver)
            bg_threads.append((pip_name, t))
            still_missing.append(pip_name)

    for imp_name, pip_name, ver, required in DEPS_AI_OPTIONAL:
        ok, _ = try_import(imp_name)
        if ok:
            st(f"Import {pip_name}")
        else:
            st(f"Installing {pip_name}...", "info")
            t = pip_install_async(pip_name, ver)
            bg_threads.append((pip_name, t))

    if still_missing:
        import time
        st(f"Waiting for {len(still_missing)} required AI packages...", "info")
        for name, t in bg_threads:
            if name in still_missing:
                t.join(timeout=120)
        time.sleep(3)

    for imp_name, pip_name, ver, required in DEPS_AI_REQUIRED:
        ok, _ = try_import(imp_name)
        if ok:
            st(f"Import {pip_name}")
        else:
            st(f"{pip_name} REQUIRED — cannot continue without AI pipeline", "fail")
            sys.exit(1)

    for imp_name, pip_name, ver, required in DEPS_AI_OPTIONAL + DEPS_OPTIONAL:
        ok, _ = try_import(imp_name)
        if ok:
            st(f"Import {pip_name}")
        else:
            st(f"{pip_name} — optional, skipping", "skip")
    print(flush=True)

    print(f"{C.BOLD}[4/7] Required Directories{C.END}", flush=True)
    for d in REQUIRED_DIRS:
        os.makedirs(os.path.join(PROJECT_DIR, d), exist_ok=True)
    st(f"{len(REQUIRED_DIRS)} directories ready")
    print(flush=True)

    print(f"{C.BOLD}[5/7] AI Models{C.END}", flush=True)
    yolov8_path = os.path.join(PROJECT_DIR, "yolov8n.pt")
    ensure_model(yolov8_path, download_yolo, "Vehicle model")

    plate_path = os.path.join(PROJECT_DIR, "license_plate.pt")
    if not os.path.exists(plate_path):
        st("License plate model: not found (using YOLOv8 general detection for plates)", "warn")
    else:
        st(f"License plate model: {os.path.basename(plate_path)}")

    reid_path = os.path.join(PROJECT_DIR, "osnet_x1_0.pth")
    if not os.path.exists(reid_path):
        st("Re-ID model: not found (using appearance-based fallback)", "warn")
    else:
        st(f"Re-ID model: {os.path.basename(reid_path)}")

    paddle_ok, _ = try_import("paddleocr")
    if paddle_ok:
        st("PaddleOCR: installed (will init lazily on first OCR request)")
    else:
        st("PaddleOCR: not installed (OCR fallback enabled)", "warn")
    print(flush=True)

    print(f"{C.BOLD}[6/7] GPU / Accelerator{C.END}", flush=True)
    try:
        import torch
        if torch.cuda.is_available():
            st(f"GPU: {torch.cuda.get_device_name(0)} (CUDA {torch.version.cuda})")
        else:
            st("GPU: not available, using CPU", "warn")
    except Exception:
        st("PyTorch not installed, using CPU", "warn")
    print(flush=True)

    print(f"{C.BOLD}[7/7] Application Initialization{C.END}", flush=True)

    db_path = os.path.join(PROJECT_DIR, "database", "navonmesh.db")
    if not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        st(f"Database: SQLite ({db_path})")
    else:
        db_url = os.environ["DATABASE_URL"]
        if "postgres" in db_url:
            st("Database: PostgreSQL")
        elif "sqlite" in db_url:
            st("Database: SQLite")
        else:
            st(f"Database: {db_url.split(':')[0]}")

    if os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
            conn.close()
            st("Database file: verified")
        except Exception:
            st("Stale database detected, recreating...", "warn")
            try:
                os.remove(db_path)
            except Exception:
                pass
            for suffix in ["-wal", "-shm"]:
                p = db_path + suffix
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            st("Database: fresh")
    else:
        st("Database: will be created on first run")

    try:
        from backend import create_app
        app = create_app()
        st("Flask application created")
    except Exception as e:
        st(f"App creation failed: {e}", "fail")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(flush=True)

    print(f"{C.BOLD}Health Check{C.END}", flush=True)
    with app.test_client() as client:
        checks = [
            ("GET /api/cameras", "/api/cameras"),
            ("GET /api/system/status", "/api/system/status"),
            ("GET /api/dashboard/stats", "/api/dashboard/stats"),
            ("GET /api/jobs", "/api/jobs"),
        ]
        for label, url in checks:
            try:
                resp = client.get(url)
                if resp.status_code == 200:
                    st(f"{label}", "ok")
                else:
                    st(f"{label} — HTTP {resp.status_code}", "warn")
            except Exception as e:
                st(f"{label} — {e}", "fail")
    print(flush=True)

    banner = (
        f"\n{C.OK}{C.BOLD}{'=' * 56}{C.END}\n"
        f"{C.OK}{C.BOLD}  NAVONMESH AI ENGINE READY{C.END}\n"
        f"{C.OK}{C.BOLD}{'=' * 56}{C.END}\n"
        f"\n"
        f"  Running at: {C.BOLD}http://127.0.0.1:5000{C.END}\n"
        f"  Dashboard:  http://127.0.0.1:5000/\n"
        f"  Upload:     http://127.0.0.1:5000/upload\n"
        f"  Tracking:   http://127.0.0.1:5000/tracking\n"
        f"  Trajectory: http://127.0.0.1:5000/trajectory\n"
        f"  Analytics:  http://127.0.0.1:5000/analytics\n"
        f"  Alerts:     http://127.0.0.1:5000/alerts\n"
        f"  Blacklist:  http://127.0.0.1:5000/blacklist\n"
        f"\n"
        f"  Press Ctrl+C to stop\n"
    )
    print(banner, flush=True)

    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    try:
        socketio = app.extensions.get("socketio")
        if socketio:
            socketio.run(app, host="0.0.0.0", port=port, debug=debug,
                         allow_unsafe_werkzeug=True)
        else:
            app.run(host="0.0.0.0", port=port, debug=debug)
    except KeyboardInterrupt:
        print(f"\n{C.WARN}Server stopped.{C.END}", flush=True)
    except Exception as e:
        print(f"\n{C.FAIL}Server error: {e}{C.END}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
