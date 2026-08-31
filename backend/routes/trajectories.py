import logging
import math
import hashlib
import time
from flask import Blueprint, render_template, request, jsonify
from backend.extensions import db

logger = logging.getLogger("navonmesh.trajectories")
trajectories_bp = Blueprint("trajectories", __name__)

SIM_CAMERA_ROUTES = [
    ["CAM-01", "CAM-02", "CAM-04"],
    ["CAM-01", "CAM-04", "CAM-03"],
    ["CAM-02", "CAM-01", "CAM-03"],
    ["CAM-02", "CAM-03", "CAM-05"],
    ["CAM-03", "CAM-01", "CAM-04"],
    ["CAM-04", "CAM-02", "CAM-05"],
    ["CAM-01", "CAM-03"],
    ["CAM-01", "CAM-04"],
    ["CAM-02", "CAM-03"],
    ["CAM-02", "CAM-05"],
    ["CAM-03", "CAM-04"],
    ["CAM-04", "CAM-05"],
    ["CAM-01", "CAM-02", "CAM-03", "CAM-04"],
    ["CAM-02", "CAM-03", "CAM-05", "CAM-06"],
    ["CAM-01", "CAM-06", "CAM-03", "CAM-05"],
    ["CAM-06", "CAM-02", "CAM-04", "CAM-05"],
]

_path_cache = {}
_path_cache_ttl = 300


def _get_cached_path(start_cam, end_cam):
    key = f"{start_cam}->{end_cam}"
    now = time.time()
    if key in _path_cache:
        cached_time, cached_path = _path_cache[key]
        if now - cached_time < _path_cache_ttl:
            return cached_path
    from backend.services.city_map import find_path
    result = find_path(start_cam, end_cam)
    _path_cache[key] = (now, result)
    return result


@trajectories_bp.route("/trajectory")
def trajectory_page():
    return render_template("trajectory.html")


def _get_camera_map():
    from backend.models.camera import Camera
    cam_map = {}
    for c in Camera.query.all():
        cam_map[c.id] = {
            "id": c.id, "name": c.name, "lat": c.lat, "lng": c.lng,
            "zone": c.zone, "status": c.status, "sourcePath": c.source_path,
        }
    return cam_map


def _get_vehicle_counts(cam_map):
    from backend.models.detection import Detection
    from backend.models.plate_read import PlateRead
    from sqlalchemy import func
    counts = {}
    for cam_id in cam_map:
        det_count = Detection.query.filter_by(camera_id=cam_id).count()
        plate_count = PlateRead.query.filter_by(camera_id=cam_id).filter(
            PlateRead.plate_text.isnot(None), PlateRead.plate_text != ""
        ).count()
        track_count = db.session.query(func.count(func.distinct(Detection.vehicle_local_id))).filter(
            Detection.camera_id == cam_id, Detection.vehicle_local_id.isnot(None)
        ).scalar() or 0
        counts[cam_id] = {"detections": det_count, "plates": plate_count, "tracks": track_count}
    return counts


def _sim_route_for_vehicle(vehicle_id):
    h = int(hashlib.md5(str(vehicle_id).encode()).hexdigest()[:8], 16)
    route_idx = h % len(SIM_CAMERA_ROUTES)
    return SIM_CAMERA_ROUTES[route_idx]


def _map_real_cam_to_city(real_camera_id):
    mapping = {
        "CAM-01": "CAM-01",
        "CAM-03": "CAM-03",
        "CAM-04": "CAM-04",
    }
    return mapping.get(real_camera_id, real_camera_id)


def _build_trajectory_data(vehicle, sightings, camera_map, camera_sequence):
    camera_sightings = {}
    for s in sightings:
        cam_id = s.camera_id or "UNKNOWN"
        if cam_id not in camera_sightings:
            camera_sightings[cam_id] = []
        camera_sightings[cam_id].append(s)

    real_cameras = set(camera_sightings.keys())
    has_multi_cam = len(real_cameras) > 1
    has_transitions = len(camera_sequence) > 1

    city_points = []
    video_points = []
    unique_cameras = []
    road_paths = []
    mode = "real"

    from backend.services.city_map import generate_road_points
    from backend.services.city_map import _load_map as load_city_map
    city_data = load_city_map()

    if has_multi_cam or has_transitions:
        mode = "real"
        all_road_points = []
        prev_cam = None

        for i, cam_id in enumerate(camera_sequence):
            city_cam_id = _map_real_cam_to_city(cam_id)
            cam_info = camera_map.get(cam_id, {})
            cam_sights = camera_sightings.get(cam_id, [])

            city_cam = city_data["cameras"].get(city_cam_id, {})
            cx = city_cam.get("x", 0)
            cy = city_cam.get("y", 0)

            unique_cameras.append({
                "cameraId": cam_id,
                "cameraName": cam_info.get("name", cam_id),
                "lat": cam_info.get("lat"),
                "lng": cam_info.get("lng"),
                "x": cx, "y": cy,
                "sightingCount": len(cam_sights),
                "firstSeen": cam_sights[0].detected_at.strftime("%H:%M:%S") if cam_sights and cam_sights[0].detected_at else "N/A",
                "lastSeen": cam_sights[-1].detected_at.strftime("%H:%M:%S") if cam_sights and cam_sights[-1].detected_at else "N/A",
                "localTrackIds": list(set(s.local_track_id for s in cam_sights if s.local_track_id)),
            })

            if prev_cam and prev_cam != city_cam_id:
                road_path = _get_cached_path(prev_cam, city_cam_id)
                if road_path:
                    road_paths.append({
                        "from": prev_cam, "to": city_cam_id,
                        "pathNodes": road_path["path"],
                        "roadIds": road_path["roads"],
                        "distance": road_path["distance"],
                        "estimatedTime": road_path["estimatedTime"],
                    })
                    road_pts = generate_road_points(road_path, num_points=max(3, len(cam_sights)))
                    for rp in road_pts:
                        all_road_points.append(rp)

            cam_road_point = {"x": cx, "y": cy}
            all_road_points.append(cam_road_point)
            prev_cam = city_cam_id

            local_ids = list(set(s.local_track_id for s in cam_sights if s.local_track_id))
            for j, s in enumerate(cam_sights):
                point = {
                    "sightingId": s.id, "cameraId": cam_id,
                    "cameraName": cam_info.get("name", cam_id),
                    "timestamp": s.detected_at.strftime("%H:%M:%S") if s.detected_at else "N/A",
                    "latitude": cam_info.get("lat"), "longitude": cam_info.get("lng"),
                    "x": cx + (j * 3 - len(cam_sights) * 1.5),
                    "y": cy + (j * 2 - len(cam_sights)),
                    "videoX": round(s.center_x, 1) if s.center_x is not None else None,
                    "videoY": round(s.center_y, 1) if s.center_y is not None else None,
                    "frameIndex": s.frame_index, "localTrackId": s.local_track_id,
                    "speed": round(s.speed, 1) if s.speed else None,
                    "ocrConfidence": round(s.ocr_confidence * 100, 1) if s.ocr_confidence else None,
                    "bbox": [s.bbox_x1, s.bbox_y1, s.bbox_x2, s.bbox_y2] if s.bbox_x1 else None,
                }
                city_points.append(point)
                if s.bbox_x1 is not None:
                    video_points.append(point)

        smooth_points = _interpolate_road_points(all_road_points, target_count=max(len(city_points), 30))
        for i, sp in enumerate(smooth_points):
            if i < len(city_points):
                city_points[i]["x"] = sp["x"]
                city_points[i]["y"] = sp["y"]

    else:
        mode = "simulation"
        sim_route = _sim_route_for_vehicle(vehicle.id)
        real_cam = camera_sequence[0] if camera_sequence else "CAM-01"
        real_city_cam = _map_real_cam_to_city(real_cam)
        real_sights = camera_sightings.get(real_cam, [])
        total_real = len(real_sights)

        cam_sight_counts = {}
        if total_real > 0:
            points_per_cam = max(1, total_real // len(sim_route))
            remainder = total_real - points_per_cam * len(sim_route)
            for idx, cam_id in enumerate(sim_route):
                cam_sight_counts[cam_id] = points_per_cam + (1 if idx < remainder else 0)
        else:
            for cam_id in sim_route:
                cam_sight_counts[cam_id] = 5

        full_road_geometry = []
        prev_cam = None
        for cam_id in sim_route:
            city_cam = city_data["cameras"].get(cam_id, {})
            if prev_cam:
                road_path = _get_cached_path(prev_cam, cam_id)
                if road_path:
                    road_paths.append({
                        "from": prev_cam, "to": cam_id,
                        "pathNodes": road_path["path"],
                        "roadIds": road_path["roads"],
                        "distance": road_path["distance"],
                        "estimatedTime": road_path["estimatedTime"],
                    })
                    pts = generate_road_points(road_path, num_points=max(4, cam_sight_counts.get(cam_id, 3) + 1))
                    full_road_geometry.extend(pts)
            cam_node = {"x": city_cam.get("x", 0), "y": city_cam.get("y", 0)}
            full_road_geometry.append(cam_node)
            prev_cam = cam_id

        unique_cameras_seen = {}
        for cam_id in sim_route:
            city_cam = city_data["cameras"].get(cam_id, {})
            cam_info = camera_map.get(cam_id, {})
            cam_sights = camera_sightings.get(cam_id, [])
            real_s_for_cam = camera_sightings.get(real_cam, [])

            unique_cameras_seen[cam_id] = {
                "cameraId": cam_id,
                "cameraName": city_cam.get("name", cam_info.get("name", cam_id)),
                "lat": cam_info.get("lat"),
                "lng": cam_info.get("lng"),
                "x": city_cam.get("x", 0),
                "y": city_cam.get("y", 0),
                "sightingCount": cam_sight_counts.get(cam_id, 3),
                "firstSeen": "Sim", "lastSeen": "Sim",
                "localTrackIds": list(set(s.local_track_id for s in real_s_for_cam if s.local_track_id)) if cam_id == real_cam else [],
            }

        unique_cameras = [unique_cameras_seen[c] for c in sim_route]

        total_road_pts = len(full_road_geometry)
        point_idx = 0
        for cam_id in sim_route:
            city_cam = city_data["cameras"].get(cam_id, {})
            n = cam_sight_counts.get(cam_id, 3)

            for j in range(n):
                t = point_idx / max(total_road_pts - 1, 1)
                road_idx = int(t * (total_road_pts - 1))
                road_idx = min(road_idx, total_road_pts - 1)
                rp = full_road_geometry[road_idx]

                from datetime import datetime, timedelta
                base_time = real_sights[0].detected_at if real_sights else datetime.utcnow()
                total_secs = (real_sights[-1].detected_at - base_time).total_seconds() if len(real_sights) > 1 else 300
                frac = point_idx / max(total_real, 1)
                ts = base_time.timestamp() + frac * total_secs
                ts_dt = datetime.fromtimestamp(ts)

                city_points.append({
                    "sightingId": None, "cameraId": cam_id,
                    "cameraName": city_cam.get("name", cam_id),
                    "timestamp": ts_dt.strftime("%H:%M:%S"),
                    "x": rp["x"] + (hash(str(vehicle.id) + str(point_idx)) % 8 - 4),
                    "y": rp["y"] + (hash(str(vehicle.id) + str(point_idx) + "y") % 8 - 4),
                    "latitude": camera_map.get(cam_id, {}).get("lat"),
                    "longitude": camera_map.get(cam_id, {}).get("lng"),
                    "videoX": 400 + (hash(str(vehicle.id) + str(point_idx)) % 400),
                    "videoY": 200 + (hash(str(vehicle.id) + str(point_idx) + "y") % 300),
                    "frameIndex": point_idx * 30, "localTrackId": j + 1,
                    "speed": None, "ocrConfidence": None, "bbox": None,
                })
                point_idx += 1

    transitions = []
    from backend.models.transition import CameraTransition
    db_transitions = CameraTransition.query.filter_by(vehicle_id=vehicle.id).all()
    for t in db_transitions:
        from_cam = camera_map.get(t.from_camera_id, {})
        to_cam = camera_map.get(t.to_camera_id, {})
        from_city = city_data["cameras"].get(_map_real_cam_to_city(t.from_camera_id), {})
        to_city = city_data["cameras"].get(_map_real_cam_to_city(t.to_camera_id), {})
        transitions.append({
            "from": t.from_camera_id, "to": t.to_camera_id,
            "fromLat": from_cam.get("lat"), "fromLng": from_cam.get("lng"),
            "toLat": to_cam.get("lat"), "toLng": to_cam.get("lng"),
            "fromX": from_city.get("x", 0), "fromY": from_city.get("y", 0),
            "toX": to_city.get("x", 0), "toY": to_city.get("y", 0),
            "travelTimeSeconds": t.travel_time_seconds,
            "estimatedDistanceKm": t.estimated_distance_km,
            "estimatedSpeedKmh": t.estimated_speed_kmh,
        })

    if mode == "simulation" and len(transitions) == 0 and len(camera_sequence) >= 2:
        for i in range(len(camera_sequence) - 1):
            from_cam_id = camera_sequence[i]
            to_cam_id = camera_sequence[i + 1]
            from_city = city_data["cameras"].get(_map_real_cam_to_city(from_cam_id), {})
            to_city = city_data["cameras"].get(_map_real_cam_to_city(to_cam_id), {})
            from_cam = camera_map.get(from_cam_id, {})
            to_cam = camera_map.get(to_cam_id, {})
            if from_city.get("x") and to_city.get("x"):
                dx = to_city["x"] - from_city["x"]
                dy = to_city["y"] - from_city["y"]
                dist = math.sqrt(dx * dx + dy * dy)
                travel = dist / 50.0 * 60 if dist > 0 else 300
                transitions.append({
                    "from": from_cam_id, "to": to_cam_id,
                    "fromLat": from_cam.get("lat"), "fromLng": from_cam.get("lng"),
                    "toLat": to_cam.get("lat"), "toLng": to_cam.get("lng"),
                    "fromX": from_city.get("x", 0), "fromY": from_city.get("y", 0),
                    "toX": to_city.get("x", 0), "toY": to_city.get("y", 0),
                    "travelTimeSeconds": round(travel, 1),
                    "estimatedDistanceKm": round(dist / 1000, 2),
                    "estimatedSpeedKmh": round(50, 1),
                })

    return city_points, video_points, unique_cameras, transitions, mode, road_paths


def _interpolate_road_points(all_points, target_count):
    if not all_points or target_count <= 0:
        return all_points

    total_length = 0
    segments = []
    for i in range(len(all_points) - 1):
        dx = all_points[i + 1]["x"] - all_points[i]["x"]
        dy = all_points[i + 1]["y"] - all_points[i]["y"]
        seg_len = math.sqrt(dx * dx + dy * dy)
        segments.append(seg_len)
        total_length += seg_len

    if total_length < 0.001:
        return all_points

    result = []
    for i in range(target_count):
        t = i / max(target_count - 1, 1)
        target_dist = t * total_length
        cumulative = 0
        for seg_idx, seg_len in enumerate(segments):
            if cumulative + seg_len >= target_dist - 0.001:
                seg_t = (target_dist - cumulative) / seg_len if seg_len > 0 else 0
                x = all_points[seg_idx]["x"] + seg_t * (all_points[seg_idx + 1]["x"] - all_points[seg_idx]["x"])
                y = all_points[seg_idx]["y"] + seg_t * (all_points[seg_idx + 1]["y"] - all_points[seg_idx]["y"])
                result.append({"x": round(x, 1), "y": round(y, 1)})
                break
            cumulative += seg_len

    return result


@trajectories_bp.route("/api/city-map", methods=["GET"])
def city_map_data():
    try:
        from backend.services.city_map import get_road_network
        network = get_road_network()
        return jsonify({"success": True, **network})
    except Exception as e:
        logger.error(f"City map data failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@trajectories_bp.route("/api/city-map/traffic-flow", methods=["GET"])
def city_traffic_flow():
    try:
        from backend.services.city_map import compute_traffic_flow
        flow = compute_traffic_flow()
        return jsonify({"success": True, "flow": flow})
    except Exception as e:
        logger.error(f"Traffic flow failed: {e}", exc_info=True)
        return jsonify({"success": True, "flow": []})


@trajectories_bp.route("/api/trajectory/search", methods=["GET"])
def search_vehicle():
    try:
        from backend.models.vehicle import Vehicle
        from backend.models.sighting import VehicleSighting
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify({"error": "Query required"}), 400

        q_upper = q.upper().replace(" ", "")
        vehicles = Vehicle.query.filter(
            db.or_(
                db.func.upper(Vehicle.plate_text) == q_upper,
                Vehicle.global_id.ilike(f"%{q}%"),
                Vehicle.plate_text.ilike(f"%{q}%"),
            )
        ).limit(20).all()

        results = []
        for v in vehicles:
            sight_count = VehicleSighting.query.filter_by(vehicle_id=v.id).count()
            cameras = db.session.query(db.distinct(VehicleSighting.camera_id)).filter_by(
                vehicle_id=v.id
            ).all()
            results.append({
                "id": v.id, "globalId": v.global_id,
                "plate": v.plate_text or "UNKNOWN",
                "vehicleType": v.vehicle_class or "Unknown",
                "sightingCount": sight_count,
                "cameraCount": len(cameras),
                "firstSeen": v.first_seen.strftime("%d %b %Y, %H:%M") if v.first_seen else "N/A",
                "lastSeen": v.last_seen.strftime("%d %b %Y, %H:%M") if v.last_seen else "N/A",
                "watchlist": v.watchlist_status or "clear",
            })
        return jsonify({"results": results, "query": q})
    except Exception as e:
        logger.error(f"Vehicle search failed: {e}")
        return jsonify({"error": str(e)}), 500


@trajectories_bp.route("/api/trajectories", methods=["GET"])
def all_trajectories():
    try:
        from backend.models.vehicle import Vehicle
        from backend.models.sighting import VehicleSighting

        camera_map = _get_camera_map()
        vehicles = Vehicle.query.all()
        trajectories = []

        for v in vehicles:
            sightings = VehicleSighting.query.filter_by(
                vehicle_id=v.id
            ).order_by(VehicleSighting.detected_at).all()

            if not sightings:
                continue

            camera_seq = list(dict.fromkeys([s.camera_id for s in sightings if s.camera_id]))
            city_points, video_points, unique_cameras, transitions, mode, road_paths = _build_trajectory_data(
                v, sightings, camera_map, camera_seq
            )

            trajectories.append({
                "vehicle": {
                    "id": v.id, "globalId": v.global_id,
                    "plate": v.plate_text or "UNKNOWN",
                    "vehicleType": v.vehicle_class or "Unknown",
                    "watchlist": v.watchlist_status or "clear",
                },
                "cameraSequence": camera_seq,
                "cityPoints": city_points,
                "transitions": transitions,
                "uniqueCameras": unique_cameras,
                "roadPaths": road_paths,
                "mode": mode,
                "sightingCount": len(sightings),
            })

        return jsonify({
            "success": True,
            "trajectories": trajectories,
            "cameraNetwork": list(camera_map.values()),
            "counts": _get_vehicle_counts(camera_map),
        })
    except Exception as e:
        logger.error(f"All trajectories failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@trajectories_bp.route("/api/trajectory/<identifier>", methods=["GET"])
def get_trajectory(identifier):
    try:
        from backend.models.vehicle import Vehicle
        from backend.models.sighting import VehicleSighting
        from backend.models.trajectory import Trajectory
        from backend.models.plate_read import PlateRead

        identifier = identifier.strip()
        vehicle = None

        if identifier.upper().startswith("GV-") or identifier.upper().startswith("SIM-"):
            vehicle = Vehicle.query.filter(Vehicle.global_id.ilike(f"%{identifier}%")).first()
        if not vehicle:
            q_upper = identifier.upper().replace(" ", "")
            vehicle = Vehicle.query.filter(db.func.upper(Vehicle.plate_text) == q_upper).first()
        if not vehicle:
            vehicle = Vehicle.query.filter(Vehicle.plate_text.ilike(f"%{identifier}%")).first()
        if not vehicle:
            vehicle = Vehicle.query.filter(Vehicle.global_id.ilike(f"%{identifier}%")).first()
        if not vehicle:
            return jsonify({"error": "Vehicle not found", "query": identifier}), 404

        sightings = VehicleSighting.query.filter_by(
            vehicle_id=vehicle.id
        ).order_by(VehicleSighting.detected_at).all()

        camera_map = _get_camera_map()
        camera_sequence = list(dict.fromkeys([s.camera_id for s in sightings if s.camera_id]))

        city_points, video_points, unique_cameras, transitions, mode, road_paths = _build_trajectory_data(
            vehicle, sightings, camera_map, camera_sequence
        )

        trajectory = Trajectory.query.filter_by(vehicle_id=vehicle.id).first()

        first_seen = sightings[0].detected_at if sightings else None
        last_seen = sightings[-1].detected_at if sightings else None
        duration_secs = (last_seen - first_seen).total_seconds() if first_seen and last_seen else 0

        readings = PlateRead.query.filter_by(vehicle_id=vehicle.id).all()
        evidence = []
        for r in readings:
            if r.crop_path:
                import os
                crop_file = os.path.basename(r.crop_path)
                evidence.append({
                    "plateText": r.plate_text,
                    "ocrConfidence": round(r.ocr_confidence * 100, 1) if r.ocr_confidence else 0,
                    "cameraId": r.camera_id,
                    "timestamp": r.detected_at.strftime("%H:%M:%S") if r.detected_at else "N/A",
                    "evidenceCrop": f"/api/evidence/{r.camera_id or 'JOB-00001'}/{crop_file}" if crop_file else None,
                    "localTrackId": r.vehicle_local_id,
                })

        return jsonify({
            "success": True,
            "vehicle": {
                "id": vehicle.id, "globalId": vehicle.global_id,
                "plate": vehicle.plate_text or "UNKNOWN",
                "vehicleType": vehicle.vehicle_class or "Unknown",
                "color": vehicle.color or "Unknown",
                "firstSeen": vehicle.first_seen.strftime("%d %b %Y, %H:%M:%S") if vehicle.first_seen else "N/A",
                "lastSeen": vehicle.last_seen.strftime("%d %b %Y, %H:%M:%S") if vehicle.last_seen else "N/A",
                "avgSpeed": round(vehicle.avg_speed, 1) if vehicle.avg_speed else 0,
                "totalDistance": round(vehicle.total_distance, 2) if vehicle.total_distance else 0,
                "watchlist": vehicle.watchlist_status or "clear",
                "ocrConfidence": round(vehicle.ocr_confidence * 100, 1) if vehicle.ocr_confidence else 0,
            },
            "summary": {
                "totalSightings": len(sightings),
                "uniqueCameras": len(unique_cameras),
                "durationSeconds": round(duration_secs, 1),
                "durationFormatted": _format_duration(duration_secs),
                "cameraSequence": camera_sequence,
            },
            "cameraNetwork": list(camera_map.values()),
            "uniqueCameras": unique_cameras,
            "cityPoints": city_points,
            "videoPoints": video_points,
            "transitions": transitions,
            "roadPaths": road_paths,
            "evidence": evidence,
            "mode": mode,
            "trajectory": trajectory.to_dict() if trajectory else None,
        })
    except Exception as e:
        logger.error(f"Trajectory search failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def _format_duration(secs):
    if secs <= 0:
        return "N/A"
    hours = int(secs // 3600)
    mins = int((secs % 3600) // 60)
    s = int(secs % 60)
    if hours > 0:
        return f"{hours}h {mins}m {s}s"
    elif mins > 0:
        return f"{mins}m {s}s"
    else:
        return f"{s}s"


@trajectories_bp.route("/api/cameras/network", methods=["GET"])
def camera_network():
    try:
        camera_map = _get_camera_map()
        counts = _get_vehicle_counts(camera_map)
        cam_list = []
        for c in camera_map.values():
            cam_list.append({**c, **counts.get(c["id"], {})})

        from backend.models.transition import CameraTransition
        from sqlalchemy import func
        transitions = db.session.query(
            CameraTransition.from_camera_id,
            CameraTransition.to_camera_id,
            func.count(CameraTransition.id).label("count"),
        ).group_by(
            CameraTransition.from_camera_id,
            CameraTransition.to_camera_id
        ).all()

        edges = []
        for t in transitions:
            from_cam = camera_map.get(t.from_camera_id, {})
            to_cam = camera_map.get(t.to_camera_id, {})
            if from_cam.get("lat") and from_cam.get("lat"):
                edges.append({
                    "from": t.from_camera_id, "to": t.to_camera_id,
                    "fromLat": from_cam["lat"], "fromLng": from_cam["lng"],
                    "toLat": to_cam["lat"], "toLng": to_cam["lng"],
                    "count": t.count,
                })

        return jsonify({"cameras": cam_list, "edges": edges})
    except Exception as e:
        logger.error(f"Camera network failed: {e}")
        return jsonify({"cameras": [], "edges": []}), 200
