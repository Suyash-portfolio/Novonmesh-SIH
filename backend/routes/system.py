import os
import logging
from flask import Blueprint, jsonify
from backend.extensions import db

logger = logging.getLogger("navonmesh.system")
system_bp = Blueprint("system", __name__)


@system_bp.route("/api/system/status", methods=["GET"])
def system_status():
    status = {}

    try:
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
        status["database"] = "ONLINE"
    except Exception as e:
        status["database"] = f"OFFLINE: {e}"

    try:
        from backend.extensions import redis_client
        if redis_client.client:
            redis_client.client.ping()
            status["redis"] = "ONLINE"
        else:
            status["redis"] = "OFFLINE"
    except Exception:
        status["redis"] = "OFFLINE"

    try:
        from backend.services.ai_models import (
            load_vehicle_detector, load_plate_detector,
            load_reid_model, OCR_INIT_ATTEMPTED, OCR_ENGINE,
        )
        try:
            model = load_vehicle_detector()
            status["vehicle_model"] = "READY" if model else "MISSING_MODEL"
        except Exception as e:
            status["vehicle_model"] = f"ERROR: {e}"

        try:
            model = load_plate_detector()
            status["plate_model"] = "READY" if model and model is not False else "MISSING_MODEL"
        except Exception as e:
            status["plate_model"] = f"ERROR: {e}"

        if OCR_INIT_ATTEMPTED and OCR_ENGINE:
            status["ocr"] = "READY"
        elif OCR_INIT_ATTEMPTED:
            status["ocr"] = "FALLBACK (pytesseract/contour)"
        else:
            status["ocr"] = "NOT_INITIALIZED (will init on first OCR request)"

        try:
            model = load_reid_model()
            status["reid"] = "READY" if model and model.get("ready") else "MISSING_MODEL"
        except Exception as e:
            status["reid"] = f"ERROR: {e}"
    except Exception:
        status["vehicle_model"] = "ERROR"
        status["plate_model"] = "ERROR"
        status["ocr"] = "ERROR"
        status["reid"] = "ERROR"

    try:
        import torch
        status["gpu"] = torch.cuda.is_available()
    except (ImportError, Exception):
        status["gpu"] = False

    try:
        from backend.models.job import ProcessingJob
        active_jobs = ProcessingJob.query.filter_by(status="PROCESSING").count()
        status["active_jobs"] = active_jobs
    except Exception:
        status["active_jobs"] = 0

    status["application"] = "ONLINE"

    return jsonify(status)


@system_bp.route("/api/dashboard/stats", methods=["GET"])
def dashboard_stats():
    try:
        from backend.models.vehicle import Vehicle
        from backend.models.detection import Detection
        from backend.models.alert import Alert
        from backend.models.plate_read import PlateRead
        from backend.models.job import ProcessingJob
        from backend.models.sighting import VehicleSighting
        from backend.models.transition import CameraTransition
        from backend.models.camera import Camera
        from datetime import datetime, timedelta

        total_vehicles_detected = Detection.query.count()
        unique_vehicles = Vehicle.query.count()
        active_alerts = Alert.query.filter_by(status="open").count()

        completed_jobs = ProcessingJob.query.filter_by(status="COMPLETED").all()
        total_sources = len(set(j.video_filename for j in completed_jobs if j.video_filename))

        cameras = Camera.query.filter(Camera.id.like("CAM-%")).count()

        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_detections = Detection.query.filter(Detection.detected_at >= today).count()

        total_plate_reads = PlateRead.query.filter(
            PlateRead.plate_text.isnot(None),
            PlateRead.plate_text != "",
        ).count()

        unique_plate_text = db.session.query(
            db.func.count(db.distinct(PlateRead.plate_text))
        ).filter(
            PlateRead.plate_text.isnot(None),
            PlateRead.plate_text != "",
        ).scalar() or 0

        vehicles_with_plates = Vehicle.query.filter(
            Vehicle.plate_text.isnot(None),
            Vehicle.plate_text != "",
        ).count()

        avg_ocr = db.session.query(
            db.func.avg(PlateRead.ocr_confidence)
        ).filter(
            PlateRead.ocr_confidence > 0,
            PlateRead.detected_at >= today - timedelta(days=1)
        ).scalar()
        avg_ocr_pct = round((avg_ocr or 0) * 100, 1)

        critical_alerts = Alert.query.filter_by(status="open", severity="critical").count()
        warning_alerts = Alert.query.filter_by(status="open", severity="warning").count()

        camera_transitions = CameraTransition.query.count()
        vehicles_on_multiple = 0
        for v in Vehicle.query.all():
            cam_ids = set()
            for s in VehicleSighting.query.filter_by(vehicle_id=v.id).all():
                if s.camera_id:
                    cam_ids.add(s.camera_id)
            if len(cam_ids) > 1:
                vehicles_on_multiple += 1

        traffic_density = min(100, round(today_detections / max(total_sources * 50, 1) * 100, 1))

        return jsonify({
            "totalSources": total_sources,
            "totalVehiclesDetected": total_vehicles_detected,
            "uniqueVehicles": unique_vehicles,
            "totalPlateReads": total_plate_reads,
            "uniquePlates": unique_plate_text,
            "vehiclesWithPlates": vehicles_with_plates,
            "activeAlerts": active_alerts,
            "criticalAlerts": critical_alerts,
            "warningAlerts": warning_alerts,
            "trafficDensity": traffic_density,
            "avgOcrConfidence": avg_ocr_pct,
            "cameraCount": cameras,
            "cameraTransitions": camera_transitions,
            "vehiclesOnMultipleCameras": vehicles_on_multiple,
        })
    except Exception as e:
        logger.error(f"Dashboard stats failed: {e}")
        return jsonify({
            "totalSources": 0,
            "totalVehiclesDetected": 0,
            "uniqueVehicles": 0,
            "activeAlerts": 0,
            "criticalAlerts": 0,
            "warningAlerts": 0,
            "trafficDensity": 0,
            "avgOcrConfidence": 0,
            "cameraCount": 0,
            "cameraTransitions": 0,
            "vehiclesOnMultipleCameras": 0,
        }), 200
