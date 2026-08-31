import logging
from flask import Blueprint, request, jsonify
from backend.extensions import db

logger = logging.getLogger("navonmesh.detections")
detections_bp = Blueprint("detections", __name__)


@detections_bp.route("/api/detections", methods=["GET"])
def get_detections():
    try:
        from backend.models.detection import Detection
        camera_id = request.args.get("camera_id")
        limit = request.args.get("limit", 50, type=int)

        query = Detection.query.order_by(Detection.detected_at.desc())
        if camera_id:
            query = query.filter_by(camera_id=camera_id)

        detections = query.limit(limit).all()
        return jsonify([d.to_dict() for d in detections])
    except Exception as e:
        logger.error(f"Failed to load detections: {e}")
        return jsonify([]), 200


@detections_bp.route("/api/detections/recent", methods=["GET"])
def get_recent_detections():
    try:
        from backend.models.plate_read import PlateRead
        from backend.models.detection import Detection

        limit = request.args.get("limit", 10, type=int)

        recent_reads = PlateRead.query.filter(
            PlateRead.plate_text.isnot(None)
        ).order_by(PlateRead.detected_at.desc()).limit(limit).all()

        result = []
        for read in recent_reads:
            det_class = "Unknown"
            if read.detection_id:
                det = Detection.query.get(read.detection_id)
                if det:
                    det_class = det.vehicle_class

            result.append({
                "plate": read.plate_text,
                "camera": read.camera_id,
                "time": read.detected_at.strftime("%H:%M:%S") if read.detected_at else "N/A",
                "type": det_class,
                "confidence": round(read.ocr_confidence * 100, 1) if read.ocr_confidence else 0,
            })

        if not result:
            recent_dets = Detection.query.order_by(
                Detection.detected_at.desc()
            ).limit(limit).all()

            for det in recent_dets:
                result.append({
                    "plate": None,
                    "camera": det.camera_id,
                    "time": det.detected_at.strftime("%H:%M:%S") if det.detected_at else "N/A",
                    "type": det.vehicle_class or "Unknown",
                    "confidence": round(det.confidence * 100, 1) if det.confidence else 0,
                    "trackId": det.vehicle_local_id,
                    "frame": det.frame_index,
                })

        return jsonify(result)
    except Exception as e:
        logger.error(f"Failed to load recent detections: {e}")
        return jsonify([]), 200
