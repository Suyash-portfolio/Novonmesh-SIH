import logging
from flask import Blueprint, render_template, jsonify, request
from backend.extensions import db

logger = logging.getLogger("navonmesh.cameras")
cameras_bp = Blueprint("cameras", __name__)


@cameras_bp.route("/cameras")
def cameras_page():
    return render_template("cameras.html")


@cameras_bp.route("/api/cameras", methods=["GET"])
def get_cameras():
    try:
        from backend.models.camera import Camera
        cameras = Camera.query.all()
        return jsonify([c.to_dict() for c in cameras])
    except Exception as e:
        logger.warning(f"Camera query failed: {e}")
        return jsonify([])


@cameras_bp.route("/api/cameras/<camera_id>", methods=["GET"])
def get_camera(camera_id):
    try:
        from backend.models.camera import Camera
        cam = Camera.query.get(camera_id)
        if not cam:
            return jsonify({"error": "Camera not found"}), 404
        return jsonify(cam.to_dict())
    except Exception as e:
        logger.error(f"Failed to load camera {camera_id}: {e}")
        return jsonify({"error": str(e)}), 500


@cameras_bp.route("/api/cameras", methods=["POST"])
def create_camera():
    try:
        from backend.models.camera import Camera
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        existing = Camera.query.get(data.get("id"))
        if existing:
            return jsonify({"error": "Camera ID already exists"}), 409

        cam = Camera(
            id=data["id"],
            name=data["name"],
            zone=data.get("zone", "Default"),
            lat=data.get("lat", 0),
            lng=data.get("lng", 0),
            map_x=data.get("x", 50),
            map_y=data.get("y", 50),
            fps=data.get("fps", 25),
            resolution=data.get("resolution", "1920x1080"),
            source_path=data.get("sourcePath"),
            status="online",
        )
        db.session.add(cam)
        db.session.commit()
        return jsonify(cam.to_dict()), 201
    except Exception as e:
        logger.error(f"Failed to create camera: {e}")
        return jsonify({"error": str(e)}), 500


@cameras_bp.route("/api/cameras/<camera_id>", methods=["PUT"])
def update_camera(camera_id):
    try:
        from backend.models.camera import Camera
        cam = Camera.query.get(camera_id)
        if not cam:
            return jsonify({"error": "Camera not found"}), 404

        data = request.get_json()
        for field in ["name", "zone", "lat", "lng", "status", "fps", "resolution", "source_path"]:
            if field in data:
                setattr(cam, field, data[field])
        if "map_x" in data:
            cam.map_x = data["map_x"]
        if "map_y" in data:
            cam.map_y = data["map_y"]
        if "sourcePath" in data:
            cam.source_path = data["sourcePath"]

        db.session.commit()
        return jsonify(cam.to_dict())
    except Exception as e:
        logger.error(f"Failed to update camera {camera_id}: {e}")
        return jsonify({"error": str(e)}), 500


@cameras_bp.route("/api/cameras/<camera_id>", methods=["DELETE"])
def delete_camera(camera_id):
    try:
        from backend.models.camera import Camera
        cam = Camera.query.get(camera_id)
        if not cam:
            return jsonify({"error": "Camera not found"}), 404
        db.session.delete(cam)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Failed to delete camera {camera_id}: {e}")
        return jsonify({"error": str(e)}), 500
