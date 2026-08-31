import os
import logging
import cv2
from flask import Blueprint, jsonify, send_from_directory, request

logger = logging.getLogger("navonmesh.videos")
videos_bp = Blueprint("videos", __name__)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOADS_DIR = os.path.join(PROJECT_DIR, "uploads")
OUTPUTS_DIR = os.path.join(PROJECT_DIR, "outputs")

ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "wmv", "webm"}


def _scan_videos():
    videos = []
    if not os.path.isdir(UPLOADS_DIR):
        return videos

    camera_map = {}
    try:
        from backend.extensions import db
        from sqlalchemy import text
        result = db.session.execute(
            text("SELECT video_filename, camera_id FROM processing_jobs WHERE camera_id IS NOT NULL")
        )
        for row in result:
            if row[0] and row[1]:
                camera_map[row[0]] = row[1]
    except Exception:
        pass

    for fname in sorted(os.listdir(UPLOADS_DIR)):
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in ALLOWED_EXTENSIONS:
            continue

        fpath = os.path.join(UPLOADS_DIR, fname)
        if not os.path.isfile(fpath):
            continue

        size = os.path.getsize(fpath)
        info = {
            "filename": fname,
            "path": fpath,
            "size": size,
            "sizeFormatted": _format_size(size),
            "duration": None,
            "fps": None,
            "width": None,
            "height": None,
            "status": "ready",
            "cameraId": camera_map.get(fname),
        }

        try:
            cap = cv2.VideoCapture(fpath)
            if cap.isOpened():
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fps_val = cap.get(cv2.CAP_PROP_FPS) or 0
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()

                info["duration"] = round(total_frames / fps_val, 1) if fps_val > 0 else 0
                info["fps"] = round(fps_val, 1)
                info["width"] = w
                info["height"] = h
            else:
                info["status"] = "unreadable"
        except Exception as e:
            logger.warning(f"Could not read video info for {fname}: {e}")
            info["status"] = "unreadable"

        videos.append(info)

    return videos


def _format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


@videos_bp.route("/api/videos", methods=["GET"])
def list_videos():
    try:
        videos = _scan_videos()
        return jsonify(videos)
    except Exception as e:
        logger.error(f"Video scan failed: {e}")
        return jsonify([]), 200


@videos_bp.route("/api/videos/<filename>/stream", methods=["GET"])
def stream_video(filename):
    try:
        safe = "".join(c for c in filename if c.isalnum() or c in "._-")
        if safe != filename:
            return jsonify({"error": "Invalid filename"}), 400

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"error": "Invalid file type"}), 400

        if not os.path.isfile(os.path.join(UPLOADS_DIR, filename)):
            return jsonify({"error": "File not found"}), 404

        return send_from_directory(UPLOADS_DIR, filename, mimetype=f"video/{ext}")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@videos_bp.route("/api/outputs/<filename>/stream", methods=["GET"])
def stream_annotated_video(filename):
    try:
        safe = "".join(c for c in filename if c.isalnum() or c in "._-")
        if safe != filename:
            return jsonify({"error": "Invalid filename"}), 400

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"error": "Invalid file type"}), 400

        fpath = os.path.join(OUTPUTS_DIR, filename)
        if not os.path.isfile(fpath):
            return jsonify({"error": "Annotated video not found"}), 404

        return send_from_directory(OUTPUTS_DIR, filename, mimetype=f"video/{ext}")
    except Exception as e:
        return jsonify({"error": str(e)}), 500
