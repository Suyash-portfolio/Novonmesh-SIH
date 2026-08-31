import logging
from flask import Blueprint, render_template, jsonify, request
from backend.extensions import db

logger = logging.getLogger("navonmesh.analytics")
analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics")
def analytics_page():
    return render_template("analytics.html")


@analytics_bp.route("/api/analytics/stats", methods=["GET"])
def get_analytics_stats():
    try:
        from backend.models.vehicle import Vehicle
        from backend.models.detection import Detection
        from backend.models.job import ProcessingJob
        from backend.models.camera import Camera
        from backend.models.sighting import VehicleSighting
        from backend.models.transition import CameraTransition
        from backend.models.plate_read import PlateRead
        from datetime import datetime, timedelta

        total_vehicles = Vehicle.query.count()

        completed_jobs = ProcessingJob.query.filter_by(status="COMPLETED").all()
        total_sources = len(set(j.video_filename for j in completed_jobs if j.video_filename))

        camera_count = Camera.query.filter(Camera.id.like("CAM-%")).count()

        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_detections = Detection.query.filter(Detection.detected_at >= today).count()

        all_detections = Detection.query.order_by(Detection.detected_at.asc()).all()

        hourly = []
        if all_detections:
            first_ts = all_detections[0].detected_at
            last_ts = all_detections[-1].detected_at
            total_secs = (last_ts - first_ts).total_seconds()
            bucket_size = max(total_secs / 12, 1)
            for i in range(12):
                b_start_secs = i * bucket_size
                b_end_secs = (i + 1) * bucket_size
                b_start_time = first_ts + timedelta(seconds=b_start_secs)
                b_end_time = first_ts + timedelta(seconds=b_end_secs)
                count = sum(1 for d in all_detections if b_start_time <= d.detected_at < b_end_time)
                mins = int(b_start_secs // 60)
                label = f"{mins}m"
                density = min(100, count // 3) if count > 0 else 0
                hourly.append({"hour": label, "vehicles": count, "density": density})

        class_counts = {}
        for d in all_detections:
            cls = d.vehicle_class or "unknown"
            class_counts[cls] = class_counts.get(cls, 0) + 1

        total_cls = sum(class_counts.values()) or 1
        vehicle_mix = [
            {"name": cls.capitalize(), "value": round(count / total_cls * 100)}
            for cls, count in sorted(class_counts.items(), key=lambda x: -x[1])[:5]
        ] or [{"name": "No Data", "value": 100}]

        transitions = CameraTransition.query.all()
        od_matrix = {}
        for t in transitions:
            key = f"{t.from_camera_id} → {t.to_camera_id}"
            if key not in od_matrix:
                od_matrix[key] = 0
            od_matrix[key] += 1

        route_frequency = [
            {"route": route, "trips": count}
            for route, count in sorted(od_matrix.items(), key=lambda x: -x[1])[:10]
        ]
        if not route_frequency:
            route_frequency = [{"route": "No multi-camera data", "trips": 0}]

        camera_flow = []
        cam_ids = [c.id for c in Camera.query.filter(Camera.id.like("CAM-%")).order_by(Camera.id).all()]
        for cam_id in cam_ids:
            det_count = Detection.query.filter_by(camera_id=cam_id).count()
            cam_flow = {
                "camera": cam_id,
                "detections": det_count,
                "flow_in": 0,
                "flow_out": 0,
            }
            for t in transitions:
                if t.to_camera_id == cam_id:
                    cam_flow["flow_in"] += 1
                if t.from_camera_id == cam_id:
                    cam_flow["flow_out"] += 1
            camera_flow.append(cam_flow)

        heatmap_buckets = []
        heatmap = []
        if all_detections:
            first_ts = all_detections[0].detected_at
            last_ts = all_detections[-1].detected_at
            total_secs = (last_ts - first_ts).total_seconds()
            bucket_size = max(total_secs / 8, 1)

            for cam_id in cam_ids:
                cam_dets = [d for d in all_detections if d.camera_id == cam_id]
                values = []
                for i in range(8):
                    b_start_secs = i * bucket_size
                    b_end_secs = (i + 1) * bucket_size
                    b_start_time = first_ts + timedelta(seconds=b_start_secs)
                    b_end_time = first_ts + timedelta(seconds=b_end_secs)
                    count = sum(1 for d in cam_dets if b_start_time <= d.detected_at < b_end_time)
                    values.append(min(100, count))
                heatmap.append({"camera": cam_id, "values": values})

            if not heatmap:
                values = []
                for i in range(8):
                    b_start_secs = i * bucket_size
                    b_end_secs = (i + 1) * bucket_size
                    b_start_time = first_ts + timedelta(seconds=b_start_secs)
                    b_end_time = first_ts + timedelta(seconds=b_end_secs)
                    count = sum(1 for d in all_detections if b_start_time <= d.detected_at < b_end_time)
                    values.append(min(100, count))
                heatmap.append({"camera": "All Detections", "values": values})

            for i in range(8):
                b_start_secs = i * bucket_size
                b_end_secs = (i + 1) * bucket_size
                mins = int(b_start_secs // 60)
                heatmap_buckets.append(f"{mins}m-{int(b_end_secs // 60)}m")

        speeds = []
        for v in Vehicle.query.filter(Vehicle.avg_speed > 0).all():
            speeds.append(v.avg_speed)
        avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 0

        congestion = "LOW"
        if today_detections > 100:
            congestion = "SEVERE"
        elif today_detections > 50:
            congestion = "HIGH"
        elif today_detections > 20:
            congestion = "MODERATE"

        density = round(today_detections / max(total_sources * 50, 1) * 100, 1)
        density = min(100, density)

        return jsonify({
            "totalVehicles": total_vehicles,
            "totalCameras": camera_count or total_sources,
            "todayDetections": today_detections,
            "trafficDensity": density,
            "hourlyTraffic": hourly,
            "vehicleMix": vehicle_mix,
            "routeFrequency": route_frequency,
            "heatmap": heatmap,
            "heatmapBuckets": heatmap_buckets,
            "odMatrix": od_matrix,
            "cameraFlow": camera_flow,
            "avgSpeed": avg_speed,
            "congestion": congestion,
            "cameraTransitions": len(transitions),
        })
    except Exception as e:
        logger.error(f"Analytics stats failed: {e}")
        return jsonify({
            "totalVehicles": 0,
            "totalCameras": 0,
            "todayDetections": 0,
            "trafficDensity": 0,
            "hourlyTraffic": [],
            "vehicleMix": [{"name": "No Data", "value": 100}],
            "routeFrequency": [{"route": "No data", "trips": 0}],
            "heatmap": [],
            "heatmapBuckets": [],
            "odMatrix": {},
            "cameraFlow": [],
            "avgSpeed": 0,
            "congestion": "LOW",
            "cameraTransitions": 0,
        }), 200


@analytics_bp.route("/api/analytics/heatmap", methods=["GET"])
def get_heatmap():
    try:
        from backend.models.detection import Detection
        from backend.models.camera import Camera
        from datetime import timedelta

        all_dets = Detection.query.order_by(Detection.detected_at.asc()).all()

        heatmap = []
        buckets = []

        cam_ids = [c.id for c in Camera.query.filter(Camera.id.like("CAM-%")).order_by(Camera.id).all()]

        if all_dets:
            first_ts = all_dets[0].detected_at
            last_ts = all_dets[-1].detected_at
            total_secs = (last_ts - first_ts).total_seconds()
            bucket_size = max(total_secs / 8, 1)

            for cam_id in cam_ids:
                cam_dets = [d for d in all_dets if d.camera_id == cam_id]
                values = []
                for i in range(8):
                    b_start_secs = i * bucket_size
                    b_end_secs = (i + 1) * bucket_size
                    b_start_time = first_ts + timedelta(seconds=b_start_secs)
                    b_end_time = first_ts + timedelta(seconds=b_end_secs)
                    count = sum(1 for d in cam_dets if b_start_time <= d.detected_at < b_end_time)
                    values.append(min(100, count))
                heatmap.append({"camera": cam_id, "values": values})

            if not heatmap:
                values = []
                for i in range(8):
                    b_start_secs = i * bucket_size
                    b_end_secs = (i + 1) * bucket_size
                    b_start_time = first_ts + timedelta(seconds=b_start_secs)
                    b_end_time = first_ts + timedelta(seconds=b_end_secs)
                    count = sum(1 for d in all_dets if b_start_time <= d.detected_at < b_end_time)
                    values.append(min(100, count))
                heatmap.append({"camera": "All Detections", "values": values})

            for i in range(8):
                b_start_secs = i * bucket_size
                b_end_secs = (i + 1) * bucket_size
                mins = int(b_start_secs // 60)
                buckets.append(f"{mins}m-{int(b_end_secs // 60)}m")

        return jsonify({"heatmap": heatmap, "buckets": buckets})
    except Exception as e:
        logger.error(f"Heatmap failed: {e}")
        return jsonify({"heatmap": [], "buckets": []}), 200
