import os
import logging
from flask import Blueprint, send_from_directory, jsonify, request

logger = logging.getLogger("navonmesh.evidence")
evidence_bp = Blueprint("evidence", __name__)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVIDENCE_DIR = os.path.join(PROJECT_DIR, "evidence")


@evidence_bp.route("/api/evidence/<job_id>/<filename>", methods=["GET"])
def serve_evidence(job_id, filename):
    try:
        safe_job_id = "".join(c for c in str(job_id) if c.isalnum() or c in "-_")
        safe_filename = "".join(c for c in str(filename) if c.isalnum() or c in "-_.")
        if not safe_job_id or not safe_filename:
            return jsonify({"error": "Invalid path"}), 400

        job_dir = os.path.join(EVIDENCE_DIR, safe_job_id)
        if not os.path.isdir(job_dir):
            return jsonify({"error": "Evidence directory not found"}), 404

        filepath = os.path.join(job_dir, safe_filename)
        if not os.path.isfile(filepath):
            return jsonify({"error": "Evidence file not found"}), 404

        return send_from_directory(job_dir, safe_filename, mimetype="image/jpeg")
    except Exception as e:
        logger.error(f"Evidence serve failed: {e}")
        return jsonify({"error": str(e)}), 500


@evidence_bp.route("/api/evidence/<job_id>", methods=["GET"])
def list_evidence(job_id):
    try:
        safe_job_id = "".join(c for c in str(job_id) if c.isalnum() or c in "-_")
        job_dir = os.path.join(EVIDENCE_DIR, safe_job_id)
        if not os.path.isdir(job_dir):
            return jsonify([]), 200

        files = []
        for f in sorted(os.listdir(job_dir)):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                size = os.path.getsize(os.path.join(job_dir, f))
                files.append({"filename": f, "size": size})
        return jsonify(files)
    except Exception as e:
        return jsonify([]), 200
