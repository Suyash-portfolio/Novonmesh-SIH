import os
import uuid
import logging
import threading
import cv2
import numpy as np
from datetime import datetime
from backend.extensions import db, socketio
from backend.services import ai_models

logger = logging.getLogger("navonmesh.processor")

_jobs = {}
_lock = threading.Lock()

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVIDENCE_DIR = os.path.join(PROJECT_DIR, "evidence")
OUTPUTS_DIR = os.path.join(PROJECT_DIR, "outputs")


def get_job_status(job_id):
    with _lock:
        return _jobs.get(job_id)


def _save_evidence_frame(frame, job_id, vehicle_local_id, frame_type="vehicle"):
    try:
        job_dir = os.path.join(EVIDENCE_DIR, str(job_id))
        os.makedirs(job_dir, exist_ok=True)
        filename = f"{frame_type}_track{vehicle_local_id}_{uuid.uuid4().hex[:8]}.jpg"
        filepath = os.path.join(job_dir, filename)
        cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return filepath
    except Exception as e:
        logger.warning(f"Failed to save evidence frame: {e}")
        return None


def _draw_annotations(frame, frame_detections, frame_idx, fps, source_label="VIDEO"):
    annotated = frame.copy()
    h, w = annotated.shape[:2]

    overlay = annotated.copy()
    cv2.rectangle(overlay, (0, 0), (w, 36), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, annotated, 0.4, 0, annotated)

    cv2.putText(annotated, f"NAVONMESH | {source_label}", (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 200), 2)

    time_str = f"{frame_idx / fps:.1f}s" if fps > 0 else f"F{frame_idx}"
    cv2.putText(annotated, time_str, (w - 100, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    status_text = f"Frame {frame_idx}"
    cv2.putText(annotated, status_text, (w - 250, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    for det in frame_detections:
        bbox = det.get("bbox", [])
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 200), 2)

        track_id = det.get("track_id", "?")
        cls = det.get("class", "vehicle")
        conf = det.get("confidence", 0)
        label = f"T{track_id} {cls} {conf:.0%}"

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(annotated, (x1, y1 - th - 10), (x1 + tw + 6, y1), (0, 255, 200), -1)
        cv2.putText(annotated, label, (x1 + 3, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        plate_bbox = det.get("plate_bbox")
        plate_text = det.get("plate_text")
        plate_conf = det.get("plate_conf", 0)

        if plate_bbox and len(plate_bbox) == 4:
            px1, py1, px2, py2 = [int(v) for v in plate_bbox]
            px1, py1 = max(0, px1), max(0, py1)
            px2, py2 = min(w, px2), min(h, py2)

            cv2.rectangle(annotated, (px1, py1), (px2, py2), (0, 0, 255), 2)

            if plate_text:
                ocr_label = f"{plate_text} {plate_conf:.0%}"
            else:
                ocr_label = "PLATE"

            (ptw, pth), _ = cv2.getTextSize(ocr_label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (px1, py1 - pth - 8), (px1 + ptw + 6, py1), (0, 0, 255), -1)
            cv2.putText(annotated, ocr_label, (px1 + 3, py1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    overlay2 = annotated.copy()
    cv2.rectangle(overlay2, (0, h - 28), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay2, 0.5, annotated, 0.5, 0, annotated)

    det_count = len(frame_detections)
    plate_count = len([d for d in frame_detections if d.get("plate_text")])
    cv2.putText(annotated, f"Detections: {det_count} | Plates Read: {plate_count}",
                (10, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

    return annotated


def _write_annotated_video(source_path, output_path, frame_annotations, fps, width, height, total_frames):
    try:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        if not out.isOpened():
            logger.warning(f"Could not open VideoWriter for {output_path}")
            return False

        cap = cv2.VideoCapture(source_path)
        if not cap.isOpened():
            return False

        frame_idx = 0
        written = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            annotations = frame_annotations.get(frame_idx, [])
            if annotations:
                frame = _draw_annotations(frame, annotations, frame_idx, fps)

            out.write(frame)
            written += 1
            frame_idx += 1

            if frame_idx % 100 == 0:
                logger.info(f"Annotated video: {written}/{total_frames} frames written")

        cap.release()
        out.release()

        logger.info(f"Annotated video written: {output_path} ({written} frames)")
        return True

    except Exception as e:
        logger.error(f"Failed to write annotated video: {e}")
        return False


def process_video_job(app, job_id, video_path, camera_id=None):
    if not camera_id:
        camera_id = "CAM-01"

    with app.app_context():
        from backend.models.job import ProcessingJob
        from backend.models.detection import Detection
        from backend.models.plate_read import PlateRead
        from backend.models.vehicle import Vehicle
        from backend.models.sighting import VehicleSighting
        from backend.models.blacklist import BlacklistEntry
        from backend.models.alert import Alert
        from backend.models.camera import Camera

        job = ProcessingJob.query.filter_by(job_id=job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        job.status = "PROCESSING"
        job.started_at = datetime.utcnow()
        db.session.commit()

        with _lock:
            _jobs[job_id] = {
                "status": "PROCESSING",
                "frames_processed": 0,
                "vehicles_detected": 0,
                "plates_detected": 0,
                "ocr_success": 0,
            }

        socketio.emit("job_status_changed", {"jobId": job_id, "status": "PROCESSING"})

        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Cannot open video: {video_path}")

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = total_frames / fps if fps > 0 else 0

            job.total_frames = total_frames
            job.video_fps = round(fps, 2)
            job.video_width = width
            job.video_height = height
            job.video_duration = round(duration, 1)
            db.session.commit()

            logger.info(
                f"Video info: {total_frames} frames, {fps:.1f} FPS, "
                f"{width}x{height}, {duration:.1f}s"
            )

            frame_skip = int(os.environ.get("FRAME_SKIP", "3"))
            frame_idx = 0
            vehicles_total = 0
            plates_total = 0
            ocr_total = 0

            local_tracks = {}
            plate_votes = {}
            track_embeddings = {}
            detection_times = {}
            track_first_frame = {}
            track_last_crop = {}
            track_last_center = {}
            track_last_frame_idx = {}
            track_speeds = {}

            frame_annotations = {}

            has_yolo = ai_models.load_vehicle_detector() is not None
            has_plate = ai_models.load_plate_detector() is not None
            logger.info(f"Models: vehicle_yolo={has_yolo}, plate_detector={has_plate}")

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % frame_skip != 0:
                    frame_idx += 1
                    continue

                detections = ai_models.detect_vehicles(frame)
                frame_annots = []

                for det in detections:
                    bbox = det["bbox"]
                    cx = (bbox[0] + bbox[2]) / 2
                    cy = (bbox[1] + bbox[3]) / 2

                    det_record = Detection(
                        job_id=job.id,
                        camera_id=camera_id,
                        frame_index=frame_idx,
                        timestamp=frame_idx / fps,
                        bbox_x1=bbox[0], bbox_y1=bbox[1],
                        bbox_x2=bbox[2], bbox_y2=bbox[3],
                        vehicle_class=det["class"],
                        confidence=det["confidence"],
                    )
                    db.session.add(det_record)
                    db.session.flush()
                    vehicles_total += 1

                    local_tid = _match_local_track(local_tracks, bbox, frame_idx)
                    det_record.vehicle_local_id = local_tid

                    if local_tid not in detection_times:
                        detection_times[local_tid] = {"first": frame_idx, "last": frame_idx, "count": 0}
                        track_first_frame[local_tid] = frame_idx
                    detection_times[local_tid]["last"] = frame_idx
                    detection_times[local_tid]["count"] += 1

                    vehicle_crop = _extract_crop(frame, bbox, padding=10)
                    track_last_crop[local_tid] = vehicle_crop

                    annot_entry = {
                        "bbox": bbox,
                        "track_id": local_tid,
                        "class": det["class"],
                        "confidence": det["confidence"],
                        "plate_bbox": None,
                        "plate_text": None,
                        "plate_conf": 0,
                    }

                    plate_result = _detect_and_ocr_plate(frame, bbox)
                    if plate_result:
                        plate_text = plate_result["plate_text"]
                        ocr_conf = plate_result["confidence"]
                        plates_total += 1

                        annot_entry["plate_bbox"] = plate_result.get("bbox")
                        annot_entry["plate_text"] = plate_text
                        annot_entry["plate_conf"] = ocr_conf

                        evidence_path = None
                        if plate_result.get("crop") is not None and plate_result["crop"].size > 0:
                            evidence_path = _save_evidence_frame(
                                plate_result["crop"], job_id, local_tid, "plate"
                            )

                        plate_record = PlateRead(
                            detection_id=det_record.id,
                            camera_id=camera_id,
                            vehicle_local_id=local_tid,
                            raw_text=plate_result.get("raw_text"),
                            plate_text=plate_text,
                            ocr_confidence=ocr_conf,
                            plate_bbox=plate_result.get("bbox"),
                            crop_path=evidence_path,
                            detected_at=datetime.utcnow(),
                        )
                        db.session.add(plate_record)

                        if plate_text and ocr_conf >= 0.3:
                            ocr_total += 1
                            track_key = f"{camera_id}_{local_tid}"
                            if track_key not in plate_votes:
                                plate_votes[track_key] = {}
                            if plate_text not in plate_votes[track_key]:
                                plate_votes[track_key][plate_text] = {"count": 0, "total_conf": 0}
                            plate_votes[track_key][plate_text]["count"] += 1
                            plate_votes[track_key][plate_text]["total_conf"] += ocr_conf

                    if local_tid not in track_embeddings and vehicle_crop is not None and vehicle_crop.size > 0:
                        emb = ai_models.compute_reid_embedding(vehicle_crop)
                        if emb:
                            track_embeddings[local_tid] = emb

                    prev_center = track_last_center.get(local_tid)
                    prev_frame = track_last_frame_idx.get(local_tid)
                    if prev_center and prev_frame:
                        dx = cx - prev_center[0]
                        dy = cy - prev_center[1]
                        pixel_dist = (dx ** 2 + dy ** 2) ** 0.5
                        frame_delta = frame_idx - prev_frame
                        time_delta = frame_delta / fps if fps > 0 else 0
                        if time_delta > 0:
                            pixels_per_sec = pixel_dist / time_delta
                            m_per_px = _estimate_meters_per_pixel(width, height)
                            speed_ms = pixels_per_sec * m_per_px
                            speed_kmh = speed_ms * 3.6
                        else:
                            speed_kmh = 0
                    else:
                        speed_kmh = 0
                        dx, dy = 0, 0

                    track_last_center[local_tid] = (cx, cy)
                    track_last_frame_idx[local_tid] = frame_idx
                    track_speeds[local_tid] = speed_kmh

                    direction = _compute_direction(dx, dy)
                    frame_annots.append(annot_entry)

                if frame_annots:
                    frame_annotations[frame_idx] = frame_annots

                if frame_idx % (frame_skip * 5) == 0 or frame_idx >= total_frames - 1:
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

                    progress = round(frame_idx / max(total_frames, 1) * 100, 1)
                    socketio.emit("job_progress", {
                        "jobId": job_id,
                        "framesProcessed": frame_idx,
                        "totalFrames": total_frames,
                        "vehiclesDetected": vehicles_total,
                        "platesDetected": plates_total,
                        "progress": progress,
                    })
                    with _lock:
                        _jobs[job_id].update({
                            "frames_processed": frame_idx,
                            "vehicles_detected": vehicles_total,
                            "plates_detected": plates_total,
                            "ocr_success": ocr_total,
                        })

                frame_idx += 1

            cap.release()

            logger.info(
                f"Video loop done: {vehicles_total} detections, "
                f"{plates_total} plate reads, {ocr_total} OCR, "
                f"{len(local_tracks)} unique tracks"
            )

            for track_key, votes in plate_votes.items():
                if not votes:
                    continue
                best_text = max(votes.keys(), key=lambda t: votes[t]["count"])
                best_entry = votes[best_text]
                final_conf = best_entry["total_conf"] / best_entry["count"]

                cam_part, local_part = track_key.rsplit("_", 1)
                local_tid = int(local_part)

                vehicle_evidence_path = None
                if local_tid in track_last_crop and track_last_crop[local_tid] is not None:
                    vehicle_evidence_path = _save_evidence_frame(
                        track_last_crop[local_tid], job_id, local_tid, "vehicle"
                    )

                vehicle = _find_or_create_vehicle(best_text, final_conf, track_embeddings.get(local_tid))
                if vehicle:
                    _update_plate_reads_for_track(cam_part, local_tid, vehicle.id, best_text)

            for tid in local_tracks:
                if f"{camera_id}_{tid}" not in plate_votes:
                    if detection_times.get(tid, {}).get("count", 0) >= 3:
                        if tid in track_last_crop and track_last_crop[tid] is not None:
                            vehicle_evidence = _save_evidence_frame(
                                track_last_crop[tid], job_id, tid, "vehicle_no_plate"
                            )
                        vehicle = _find_or_create_vehicle(
                            None, 0, track_embeddings.get(tid)
                        )

            _create_sightings_from_detections(camera_id)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

            _check_blacklist_alerts(camera_id)
            _update_vehicle_trajectories(camera_id)

            annotated_filename = f"{job_id}_annotated.mp4"
            os.makedirs(OUTPUTS_DIR, exist_ok=True)
            annotated_path = os.path.join(OUTPUTS_DIR, annotated_filename)

            source_basename = os.path.basename(video_path)
            logger.info(f"Generating annotated video: {annotated_filename}")
            _write_annotated_video(
                video_path, annotated_path,
                frame_annotations, fps, width, height, total_frames
            )

            job.status = "COMPLETED"
            job.frames_processed = frame_idx
            job.vehicles_detected = vehicles_total
            job.plates_detected = plates_total
            job.ocr_successes = ocr_total
            job.output_video = annotated_path
            job.completed_at = datetime.utcnow()
            db.session.commit()

            with _lock:
                _jobs[job_id].update({
                    "status": "COMPLETED",
                    "frames_processed": frame_idx,
                    "vehicles_detected": vehicles_total,
                    "plates_detected": plates_total,
                    "ocr_success": ocr_total,
                    "annotated_video": annotated_filename,
                })

            socketio.emit("job_status_changed", {
                "jobId": job_id, "status": "COMPLETED",
                "vehiclesDetected": vehicles_total,
                "platesDetected": plates_total,
                "annotatedVideo": annotated_filename,
            })

            logger.info(
                f"Job {job_id} completed: {frame_idx} frames, "
                f"{vehicles_total} vehicles, {plates_total} plates, {ocr_total} OCR, "
                f"annotated: {annotated_filename}"
            )

            _schedule_cross_camera_matching(app)

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            try:
                job.status = "FAILED"
                job.error_message = str(e)
                db.session.commit()
            except Exception:
                pass
            with _lock:
                if job_id in _jobs:
                    _jobs[job_id]["status"] = "FAILED"
            socketio.emit("job_status_changed", {"jobId": job_id, "status": "FAILED"})


def _schedule_cross_camera_matching(app):
    import threading

    def _delayed_match():
        import time
        time.sleep(2)
        try:
            run_cross_camera_matching(app)
        except Exception as e:
            logger.error(f"Cross-camera matching failed: {e}")

    thread = threading.Thread(target=_delayed_match, daemon=True)
    thread.start()


def _match_local_track(tracks, bbox, frame_idx, max_distance=120):
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2

    best_id = None
    best_dist = max_distance

    for tid, info in tracks.items():
        if frame_idx - info["last_frame"] > 30:
            continue
        pcx, pcy = info["center"]
        dist = ((cx - pcx) ** 2 + (cy - pcy) ** 2) ** 0.5
        if dist < best_dist:
            best_dist = dist
            best_id = tid

    if best_id is not None:
        tracks[best_id] = {"center": (cx, cy), "last_frame": frame_idx}
        return best_id

    new_id = max(tracks.keys(), default=0) + 1
    tracks[new_id] = {"center": (cx, cy), "last_frame": frame_idx}
    return new_id


def _detect_and_ocr_plate(frame, vehicle_bbox):
    plate_result = ai_models.detect_plate(frame, vehicle_bbox)
    if plate_result and plate_result.get("crop") is not None:
        ocr_result = ai_models.run_ocr(plate_result["crop"])
        return {
            "raw_text": ocr_result.get("raw_text"),
            "plate_text": ocr_result.get("plate_text"),
            "confidence": ocr_result.get("confidence", 0.0),
            "bbox": plate_result.get("bbox"),
            "crop": plate_result.get("crop"),
        }
    return None


def _extract_crop(frame, bbox, padding=10):
    h, w = frame.shape[:2]
    x1 = max(0, int(bbox[0]) - padding)
    y1 = max(0, int(bbox[1]) - padding)
    x2 = min(w, int(bbox[2]) + padding)
    y2 = min(h, int(bbox[3]) + padding)
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2].copy()


def _estimate_meters_per_pixel(frame_width, frame_height):
    avg_road_width_m = 10.0
    avg_road_width_px = frame_width * 0.4
    if avg_road_width_px > 0:
        return avg_road_width_m / avg_road_width_px
    return 0.05


def _compute_direction(dx, dy):
    if abs(dx) < 5 and abs(dy) < 5:
        return "Stationary"
    angle = np.degrees(np.arctan2(-dy, dx))
    if -22.5 <= angle < 22.5:
        return "Left"
    elif 22.5 <= angle < 67.5:
        return "Up-Left"
    elif 67.5 <= angle < 112.5:
        return "Up"
    elif 112.5 <= angle < 157.5:
        return "Up-Right"
    elif angle >= 157.5 or angle < -157.5:
        return "Right"
    elif -157.5 <= angle < -112.5:
        return "Down-Right"
    elif -112.5 <= angle < -67.5:
        return "Down"
    elif -67.5 <= angle < -22.5:
        return "Down-Left"
    return "Unknown"


def _find_or_create_vehicle(plate_text, ocr_conf, embedding=None):
    from backend.models.vehicle import Vehicle

    if plate_text:
        existing = Vehicle.query.filter_by(plate_text=plate_text).first()
        if existing:
            existing.last_seen = datetime.utcnow()
            existing.ocr_confidence = max(existing.ocr_confidence or 0, ocr_conf)
            if embedding:
                existing.reid_embedding = embedding
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            return existing

    global_id = _generate_global_id()
    vehicle = Vehicle(
        global_id=global_id,
        plate_text=plate_text,
        ocr_confidence=ocr_conf,
        reid_embedding=embedding,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
    )
    db.session.add(vehicle)
    db.session.flush()
    return vehicle


def _generate_global_id():
    from backend.models.vehicle import Vehicle
    import uuid
    while True:
        candidate = f"GV-{uuid.uuid4().hex[:8].upper()}"
        existing = Vehicle.query.filter_by(global_id=candidate).first()
        if not existing:
            return candidate


def _record_sighting(vehicle_id, camera_id, local_tid, plate_text, ocr_conf, frame_idx, fps,
                     center_x=0, center_y=0, speed_kmh=0, real_frame_idx=None):
    from backend.models.sighting import VehicleSighting

    sighting = VehicleSighting(
        vehicle_id=vehicle_id,
        camera_id=camera_id,
        local_track_id=local_tid,
        detected_at=datetime.utcnow(),
        direction=None,
        speed=round(speed_kmh, 1) if speed_kmh > 0 else None,
        lane=None,
        ocr_confidence=ocr_conf,
        frame_index=real_frame_idx or frame_idx,
        center_x=round(center_x, 1),
        center_y=round(center_y, 1),
    )
    db.session.add(sighting)
    db.session.flush()


def _create_sightings_from_detections(camera_id):
    from backend.models.detection import Detection
    from backend.models.sighting import VehicleSighting
    from backend.models.vehicle import Vehicle
    from backend.models.plate_read import PlateRead

    track_to_vehicle = {}
    reads = PlateRead.query.filter(
        PlateRead.vehicle_id.isnot(None),
        PlateRead.vehicle_local_id.isnot(None),
    ).all()
    for r in reads:
        key = (r.camera_id, r.vehicle_local_id)
        if key not in track_to_vehicle:
            track_to_vehicle[key] = r.vehicle_id

    all_dets = Detection.query.filter_by(camera_id=camera_id).all()
    for d in all_dets:
        vehicle_id = None
        if d.vehicle_id:
            vehicle_id = d.vehicle_id
        else:
            key = (camera_id, d.vehicle_local_id)
            if key in track_to_vehicle:
                vehicle_id = track_to_vehicle[key]

        if not vehicle_id:
            continue

        cx = (d.bbox_x1 + d.bbox_x2) / 2 if d.bbox_x1 and d.bbox_x2 else 0
        cy = (d.bbox_y1 + d.bbox_y2) / 2 if d.bbox_y1 and d.bbox_y2 else 0

        existing = VehicleSighting.query.filter_by(
            vehicle_id=vehicle_id,
            frame_index=d.frame_index,
            camera_id=camera_id,
        ).first()
        if existing:
            continue

        sighting = VehicleSighting(
            vehicle_id=vehicle_id,
            camera_id=camera_id,
            detection_id=d.id,
            local_track_id=d.vehicle_local_id,
            detected_at=d.detected_at or datetime.utcnow(),
            direction=None,
            speed=None,
            lane=None,
            ocr_confidence=d.confidence,
            frame_index=d.frame_index,
            center_x=round(cx, 1),
            center_y=round(cy, 1),
            bbox_x1=d.bbox_x1,
            bbox_y1=d.bbox_y1,
            bbox_x2=d.bbox_x2,
            bbox_y2=d.bbox_y2,
        )
        db.session.add(sighting)


def _update_plate_reads_for_track(camera_id, local_tid, vehicle_id, plate_text):
    from backend.models.plate_read import PlateRead
    PlateRead.query.filter_by(
        camera_id=camera_id,
        vehicle_local_id=local_tid,
    ).update({"vehicle_id": vehicle_id, "is_confirmed": True})


def _check_blacklist_alerts(camera_id):
    from backend.models.plate_read import PlateRead
    from backend.models.blacklist import BlacklistEntry
    from backend.models.alert import Alert

    recent_reads = PlateRead.query.filter_by(
        camera_id=camera_id
    ).filter(
        PlateRead.detected_at >= datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    ).all()

    for read in recent_reads:
        if not read.plate_text:
            continue
        bl = BlacklistEntry.query.filter_by(
            plate_text=read.plate_text,
            is_active=True,
        ).first()
        if bl:
            existing = Alert.query.filter_by(
                alert_type="BLACKLIST",
                plate_text=read.plate_text,
                status="open",
            ).first()
            if existing:
                continue

            alert_count = Alert.query.count()
            alert = Alert(
                alert_id=f"ALT-{alert_count + 1:05d}",
                alert_type="BLACKLIST",
                severity=bl.severity or "critical",
                plate_text=read.plate_text,
                camera_id=camera_id,
                vehicle_id=read.vehicle_id,
                detail=f"Plate {read.plate_text} matches blacklist entry: {bl.reason}",
                status="open",
            )
            db.session.add(alert)
            logger.warning(f"BLACKLIST ALERT: {read.plate_text} detected at {camera_id}")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def _update_vehicle_trajectories(camera_id):
    from backend.models.vehicle import Vehicle
    from backend.models.sighting import VehicleSighting
    from backend.models.trajectory import Trajectory

    for vehicle in Vehicle.query.all():
        sightings = VehicleSighting.query.filter_by(
            vehicle_id=vehicle.id
        ).order_by(VehicleSighting.detected_at).all()

        if len(sightings) < 2:
            continue

        total_secs = (sightings[-1].detected_at - sightings[0].detected_at).total_seconds()
        speeds = [s.speed for s in sightings if s.speed and s.speed > 0]
        avg_speed = sum(speeds) / len(speeds) if speeds else 0

        total_dist = 0.0
        for i in range(len(sightings) - 1):
            s1 = sightings[i]
            s2 = sightings[i + 1]
            if s1.center_x is not None and s1.center_y is not None and s2.center_x is not None and s2.center_y is not None:
                dx = s2.center_x - s1.center_x
                dy = s2.center_y - s1.center_y
                pixel_dist = (dx ** 2 + dy ** 2) ** 0.5
                m_per_px = _estimate_meters_per_pixel(1920, 1080)
                total_dist += pixel_dist * m_per_px

        total_dist_km = total_dist / 1000.0
        camera_seq = list(dict.fromkeys([s.camera_id for s in sightings if s.camera_id]))

        traj = Trajectory.query.filter_by(vehicle_id=vehicle.id).first()
        if traj:
            traj.total_distance_km = round(total_dist_km, 4)
            traj.total_duration_seconds = total_secs
            traj.avg_speed_kmh = round(avg_speed, 1)
            traj.camera_sequence = camera_seq
        else:
            traj = Trajectory(
                vehicle_id=vehicle.id,
                total_distance_km=round(total_dist_km, 4),
                total_duration_seconds=total_secs,
                avg_speed_kmh=round(avg_speed, 1),
                camera_sequence=camera_seq,
            )
            db.session.add(traj)

        vehicle.total_distance = round(total_dist_km, 4)
        vehicle.avg_speed = round(avg_speed, 1)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def run_cross_camera_matching(app):
    with app.app_context():
        from backend.models.vehicle import Vehicle
        from backend.models.sighting import VehicleSighting
        from backend.models.transition import CameraTransition
        from backend.models.plate_read import PlateRead
        import numpy as np

        logger.info("Starting cross-camera matching...")

        vehicles_with_plates = Vehicle.query.filter(
            Vehicle.plate_text.isnot(None),
            Vehicle.plate_text != "",
            Vehicle.plate_text != "UNKNOWN",
        ).all()

        all_vehicles = Vehicle.query.all()

        plate_map = {}
        for v in vehicles_with_plates:
            plate_key = v.plate_text.upper().strip().replace(" ", "")
            if plate_key not in plate_map:
                plate_map[plate_key] = []
            plate_map[plate_key].append(v)

        merged_count = 0
        for plate_key, vehicles in plate_map.items():
            if len(vehicles) <= 1:
                continue

            primary = vehicles[0]
            for other in vehicles[1:]:
                if other.id == primary.id:
                    continue

                other_sightings = VehicleSighting.query.filter_by(
                    vehicle_id=other.id
                ).all()
                for s in other_sightings:
                    s.vehicle_id = primary.id
                    s.ocr_confidence = s.ocr_confidence or 0

                other_plate_reads = PlateRead.query.filter_by(
                    vehicle_id=other.id
                ).all()
                for pr in other_plate_reads:
                    pr.vehicle_id = primary.id

                primary.last_seen = max(primary.last_seen or primary.created_at, other.last_seen or other.created_at)
                primary.ocr_confidence = max(primary.ocr_confidence or 0, other.ocr_confidence or 0)

                if other.reid_embedding and not primary.reid_embedding:
                    primary.reid_embedding = other.reid_embedding

                try:
                    db.session.delete(other)
                    merged_count += 1
                except Exception:
                    pass

        reid_matched = 0
        unmatched_vehicles = Vehicle.query.filter(
            Vehicle.plate_text.is_(None),
            Vehicle.reid_embedding.isnot(None),
        ).all()

        plated_vehicles = Vehicle.query.filter(
            Vehicle.plate_text.isnot(None),
            Vehicle.plate_text != "",
            Vehicle.reid_embedding.isnot(None),
        ).all()

        for uv in unmatched_vehicles:
            if uv.reid_embedding is None:
                continue
            best_match = None
            best_sim = 0.65
            for pv in plated_vehicles:
                if pv.reid_embedding is None:
                    continue
                sim = ai_models.cosine_similarity_bytes(uv.reid_embedding, pv.reid_embedding)
                if sim > best_sim:
                    best_sim = sim
                    best_match = pv
            if best_match:
                other_sightings = VehicleSighting.query.filter_by(vehicle_id=uv.id).all()
                for s in other_sightings:
                    s.vehicle_id = best_match.id
                other_reads = PlateRead.query.filter_by(vehicle_id=uv.id).all()
                for pr in other_reads:
                    pr.vehicle_id = best_match.id
                best_match.last_seen = max(best_match.last_seen or best_match.created_at, uv.last_seen or uv.created_at)
                try:
                    db.session.delete(uv)
                    reid_matched += 1
                except Exception:
                    pass

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return

        _create_camera_transitions(app)
        _update_all_trajectories(app)

        logger.info(
            f"Cross-camera matching done: {merged_count} plate merges, "
            f"{reid_matched} re-id merges"
        )


def _create_camera_transitions(app):
    from backend.models.vehicle import Vehicle
    from backend.models.sighting import VehicleSighting
    from backend.models.transition import CameraTransition

    vehicles = Vehicle.query.all()
    for vehicle in vehicles:
        sightings = VehicleSighting.query.filter_by(
            vehicle_id=vehicle.id
        ).order_by(VehicleSighting.detected_at).all()

        if len(sightings) < 2:
            continue

        cameras_seen = []
        for s in sightings:
            if s.camera_id and (not cameras_seen or cameras_seen[-1] != s.camera_id):
                cameras_seen.append(s.camera_id)

        if len(cameras_seen) < 2:
            continue

        for i in range(len(cameras_seen) - 1):
            from_cam = cameras_seen[i]
            to_cam = cameras_seen[i + 1]

            from_sighting = None
            to_sighting = None
            for s in sightings:
                if s.camera_id == from_cam and from_sighting is None:
                    from_sighting = s
                if s.camera_id == to_cam and to_sighting is None:
                    to_sighting = s

            if not from_sighting or not to_sighting:
                continue

            existing = CameraTransition.query.filter_by(
                vehicle_id=vehicle.id,
                from_camera_id=from_cam,
                to_camera_id=to_cam,
            ).first()
            if existing:
                continue

            travel_secs = (to_sighting.detected_at - from_sighting.detected_at).total_seconds()
            if travel_secs < 0:
                travel_secs = abs(travel_secs)

            est_dist = travel_secs * 0.015 if travel_secs > 0 else 0
            est_speed = (est_dist / (travel_secs / 3600)) if travel_secs > 0 else 0

            transition = CameraTransition(
                vehicle_id=vehicle.id,
                from_camera_id=from_cam,
                to_camera_id=to_cam,
                from_sighting_id=from_sighting.id,
                to_sighting_id=to_sighting.id,
                travel_time_seconds=round(travel_secs, 1),
                estimated_distance_km=round(est_dist, 4),
                estimated_speed_kmh=round(est_speed, 1),
            )
            db.session.add(transition)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def _update_all_trajectories(app):
    from backend.models.vehicle import Vehicle
    from backend.models.sighting import VehicleSighting
    from backend.models.transition import CameraTransition
    from backend.models.trajectory import Trajectory

    vehicles = Vehicle.query.all()
    for vehicle in vehicles:
        sightings = VehicleSighting.query.filter_by(
            vehicle_id=vehicle.id
        ).order_by(VehicleSighting.detected_at).all()

        transitions = CameraTransition.query.filter_by(
            vehicle_id=vehicle.id
        ).order_by(CameraTransition.created_at).all()

        speeds = [s.speed for s in sightings if s.speed and s.speed > 0]
        avg_speed = sum(speeds) / len(speeds) if speeds else 0

        total_secs = 0
        if sightings:
            total_secs = (sightings[-1].detected_at - sightings[0].detected_at).total_seconds()

        camera_seq = list(dict.fromkeys([s.camera_id for s in sightings if s.camera_id]))

        total_dist = sum(t.estimated_distance_km or 0 for t in transitions)

        traj = Trajectory.query.filter_by(vehicle_id=vehicle.id).first()
        if traj:
            traj.total_distance_km = round(total_dist, 4)
            traj.total_duration_seconds = total_secs
            traj.avg_speed_kmh = round(avg_speed, 1)
            traj.camera_sequence = camera_seq
        else:
            traj = Trajectory(
                vehicle_id=vehicle.id,
                total_distance_km=round(total_dist, 4),
                total_duration_seconds=total_secs,
                avg_speed_kmh=round(avg_speed, 1),
                camera_sequence=camera_seq,
            )
            db.session.add(traj)

        vehicle.total_distance = round(total_dist, 4)
        vehicle.avg_speed = round(avg_speed, 1)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
