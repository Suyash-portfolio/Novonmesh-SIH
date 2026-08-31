import logging
from flask import Blueprint, render_template, jsonify, request
from backend.extensions import db

logger = logging.getLogger("navonmesh.blacklist")
blacklist_bp = Blueprint("blacklist", __name__)


@blacklist_bp.route("/blacklist")
def blacklist_page():
    return render_template("blacklist.html")


@blacklist_bp.route("/api/blacklist", methods=["GET"])
def get_blacklist():
    try:
        from backend.models.blacklist import BlacklistEntry
        entries = BlacklistEntry.query.order_by(BlacklistEntry.added_at.desc()).all()
        return jsonify([e.to_dict() for e in entries])
    except Exception as e:
        logger.error(f"Failed to load blacklist: {e}")
        return jsonify([]), 200


@blacklist_bp.route("/api/blacklist", methods=["POST"])
def add_to_blacklist():
    try:
        from backend.models.blacklist import BlacklistEntry
        data = request.get_json()
        if not data or not data.get("plateText"):
            return jsonify({"error": "Plate text is required"}), 400

        plate = data["plateText"].upper().replace(" ", "")
        existing = BlacklistEntry.query.filter_by(plate_text=plate, is_active=True).first()
        if existing:
            return jsonify({"error": "Plate already blacklisted"}), 409

        entry = BlacklistEntry(
            plate_text=plate,
            reason=data.get("reason", ""),
            severity=data.get("severity", "warning"),
            is_active=True,
        )
        db.session.add(entry)
        db.session.commit()
        return jsonify(entry.to_dict()), 201
    except Exception as e:
        logger.error(f"Failed to add blacklist entry: {e}")
        return jsonify({"error": str(e)}), 500


@blacklist_bp.route("/api/blacklist/<int:entry_id>", methods=["PUT"])
def update_blacklist_entry(entry_id):
    try:
        from backend.models.blacklist import BlacklistEntry
        entry = BlacklistEntry.query.get(entry_id)
        if not entry:
            return jsonify({"error": "Blacklist entry not found"}), 404

        data = request.get_json()
        if "reason" in data:
            entry.reason = data["reason"]
        if "severity" in data:
            entry.severity = data["severity"]
        if "isActive" in data:
            entry.is_active = data["isActive"]
        if "plateText" in data:
            entry.plate_text = data["plateText"].upper().replace(" ", "")

        db.session.commit()
        return jsonify(entry.to_dict())
    except Exception as e:
        logger.error(f"Failed to update blacklist entry: {e}")
        return jsonify({"error": str(e)}), 500


@blacklist_bp.route("/api/blacklist/<int:entry_id>", methods=["DELETE"])
def delete_blacklist_entry(entry_id):
    try:
        from backend.models.blacklist import BlacklistEntry
        entry = BlacklistEntry.query.get(entry_id)
        if not entry:
            return jsonify({"error": "Blacklist entry not found"}), 404
        db.session.delete(entry)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Failed to delete blacklist entry: {e}")
        return jsonify({"error": str(e)}), 500
