import os
import logging
from flask import Blueprint, jsonify, request, render_template
from backend.extensions import db
from sqlalchemy import text

logger = logging.getLogger("navonmesh.plates")
plates_bp = Blueprint("plates", __name__)


@plates_bp.route("/plates")
def plates_page():
    return render_template("detected_plates.html")


@plates_bp.route("/api/plates", methods=["GET"])
def list_plates():
    try:
        confidence_filter = request.args.get("confidence", "all")
        search = request.args.get("search", "").strip()

        query = text("""
            SELECT
                pr.id, pr.plate_text, pr.raw_text, pr.ocr_confidence,
                pr.plate_bbox, pr.crop_path, pr.vehicle_local_id,
                pr.detected_at, pr.detection_id, pr.camera_id,
                d.frame_index, d.timestamp, d.vehicle_class,
                d.bbox_x1, d.bbox_y1, d.bbox_x2, d.bbox_y2,
                d.confidence AS det_confidence,
                v.global_id, v.plate_text AS vehicle_plate, v.id AS vehicle_db_id,
                j.job_id, j.video_filename
            FROM plate_reads pr
            LEFT JOIN detections d ON pr.detection_id = d.id
            LEFT JOIN vehicles v ON pr.vehicle_id = v.id
            LEFT JOIN processing_jobs j ON d.job_id = j.id
            WHERE pr.plate_text IS NOT NULL AND pr.plate_text != ''
        """)
        params = {}

        where_clauses = []
        if search:
            where_clauses.append("(pr.plate_text LIKE :search OR v.global_id LIKE :search OR pr.raw_text LIKE :search)")
            params["search"] = f"%{search}%"

        if confidence_filter == "high":
            where_clauses.append("pr.ocr_confidence >= 0.85")
        elif confidence_filter == "medium":
            where_clauses.append("pr.ocr_confidence >= 0.60 AND pr.ocr_confidence < 0.85")
        elif confidence_filter == "low":
            where_clauses.append("pr.ocr_confidence < 0.60")

        if where_clauses:
            query = text(str(query) + " AND " + " AND ".join(where_clauses))

        query = text(str(query) + " ORDER BY pr.ocr_confidence DESC")

        result = db.session.execute(query, params)
        rows = result.fetchall()

        plates = []
        for row in rows:
            crop_path = row.crop_path or ""
            crop_filename = os.path.basename(crop_path) if crop_path else None
            job_id = row.job_id or ""

            vehicle_bbox = None
            if row.bbox_x1 is not None:
                vehicle_bbox = [row.bbox_x1, row.bbox_y1, row.bbox_x2, row.bbox_y2]

            plates.append({
                "id": row.id,
                "plateText": row.plate_text,
                "rawText": row.raw_text,
                "ocrConfidence": round(row.ocr_confidence, 2),
                "plateBbox": row.plate_bbox,
                "trackId": row.vehicle_local_id,
                "cameraId": row.camera_id,
                "globalId": row.global_id,
                "vehiclePlate": row.vehicle_plate,
                "vehicleDbId": row.vehicle_db_id,
                "vehicleClass": row.vehicle_class or "Unknown",
                "vehicleBbox": vehicle_bbox,
                "detConfidence": round(row.det_confidence, 2) if row.det_confidence else None,
                "frameIndex": row.frame_index,
                "timestamp": round(row.timestamp, 2) if row.timestamp else 0,
                "detectedAt": row.detected_at,
                "jobId": job_id,
                "videoFilename": row.video_filename,
                "evidenceCrop": f"/api/evidence/{job_id}/{crop_filename}" if crop_filename else None,
            })

        return jsonify(plates)

    except Exception as e:
        logger.error(f"Failed to list plates: {e}", exc_info=True)
        return jsonify([]), 200


@plates_bp.route("/api/plates/summary", methods=["GET"])
def plates_summary():
    try:
        r1 = db.session.execute(text("SELECT COUNT(*) FROM plate_reads WHERE plate_text IS NOT NULL AND plate_text != ''")).scalar()
        r2 = db.session.execute(text("SELECT COUNT(DISTINCT plate_text) FROM plate_reads WHERE plate_text IS NOT NULL AND plate_text != ''")).scalar()
        r3 = db.session.execute(text("SELECT AVG(ocr_confidence) FROM plate_reads WHERE plate_text IS NOT NULL AND plate_text != ''")).scalar() or 0
        r4 = db.session.execute(text("SELECT COUNT(*) FROM plate_reads WHERE plate_text IS NOT NULL AND ocr_confidence >= 0.85")).scalar()
        r5 = db.session.execute(text("SELECT COUNT(*) FROM plate_reads WHERE plate_text IS NOT NULL AND ocr_confidence >= 0.60 AND ocr_confidence < 0.85")).scalar()
        r6 = db.session.execute(text("SELECT COUNT(*) FROM plate_reads WHERE plate_text IS NOT NULL AND ocr_confidence < 0.60")).scalar()
        vrows = db.session.execute(text("SELECT global_id, plate_text, ocr_confidence FROM vehicles WHERE plate_text IS NOT NULL AND plate_text != ''")).fetchall()

        return jsonify({
            "totalReads": r1,
            "uniquePlates": r2,
            "avgConfidence": round(r3, 2),
            "highConfidence": r4,
            "mediumConfidence": r5,
            "lowConfidence": r6,
            "vehiclesWithPlates": [{"globalId": r[0], "plate": r[1], "conf": round(r[2], 2)} for r in vrows],
        })

    except Exception as e:
        logger.error(f"Failed to get plate summary: {e}")
        return jsonify({}), 200


@plates_bp.route("/api/plates/<int:plate_id>", methods=["GET"])
def get_plate_detail(plate_id):
    try:
        row = db.session.execute(text("""
            SELECT pr.*, d.frame_index, d.timestamp, d.vehicle_class,
                   d.bbox_x1, d.bbox_y1, d.bbox_x2, d.bbox_y2,
                   d.confidence AS det_confidence,
                   v.global_id, v.plate_text AS vehicle_plate, v.id AS vehicle_db_id,
                   v.first_seen AS v_first_seen, v.last_seen AS v_last_seen,
                   j.job_id, j.video_filename
            FROM plate_reads pr
            LEFT JOIN detections d ON pr.detection_id = d.id
            LEFT JOIN vehicles v ON pr.vehicle_id = v.id
            LEFT JOIN processing_jobs j ON d.job_id = j.id
            WHERE pr.id = :pid
        """), {"pid": plate_id}).fetchone()

        if not row:
            return jsonify({"error": "Plate not found"}), 404

        crop_path = row.crop_path or ""
        crop_filename = os.path.basename(crop_path) if crop_path else None
        job_id = row.job_id or ""

        vehicle_bbox = None
        if row.bbox_x1 is not None:
            vehicle_bbox = [row.bbox_x1, row.bbox_y1, row.bbox_x2, row.bbox_y2]

        return jsonify({
            "id": row.id,
            "plateText": row.plate_text,
            "rawText": row.raw_text,
            "ocrConfidence": round(row.ocr_confidence, 2),
            "plateBbox": row.plate_bbox,
            "trackId": row.vehicle_local_id,
            "globalId": row.global_id,
            "vehiclePlate": row.vehicle_plate,
            "vehicleDbId": row.vehicle_db_id,
            "vehicleClass": row.vehicle_class or "Unknown",
            "vehicleBbox": vehicle_bbox,
            "detConfidence": round(row.det_confidence, 2) if row.det_confidence else None,
            "frameIndex": row.frame_index,
            "timestamp": round(row.timestamp, 2) if row.timestamp else 0,
            "detectedAt": row.detected_at,
            "vehicleFirstSeen": row.v_first_seen,
            "vehicleLastSeen": row.v_last_seen,
            "jobId": job_id,
            "videoFilename": row.video_filename,
            "evidenceCrop": f"/api/evidence/{job_id}/{crop_filename}" if crop_filename else None,
        })

    except Exception as e:
        logger.error(f"Failed to get plate detail: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
