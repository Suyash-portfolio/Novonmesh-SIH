import os
import uuid
import logging
from flask import Blueprint, request, jsonify, current_app, render_template
from backend.extensions import db, socketio
from werkzeug.utils import secure_filename

logger = logging.getLogger("navonmesh.upload")
upload_bp = Blueprint("upload", __name__)

ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "wmv", "webm"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _assign_camera_id():
    from backend.models.camera import Camera
    from backend.models.job import ProcessingJob

    existing_jobs = ProcessingJob.query.filter(
        ProcessingJob.camera_id.isnot(None)
    ).all()
    used_ids = set()
    for j in existing_jobs:
        if j.camera_id and j.camera_id.startswith("CAM-"):
            try:
                num = int(j.camera_id.split("-")[1])
                used_ids.add(num)
            except (IndexError, ValueError):
                pass

    existing_cameras = Camera.query.all()
    for c in existing_cameras:
        if c.id and c.id.startswith("CAM-"):
            try:
                num = int(c.id.split("-")[1])
                used_ids.add(num)
            except (IndexError, ValueError):
                pass

    next_num = 1
    while next_num in used_ids:
        next_num += 1

    return f"CAM-{next_num:02d}"


@upload_bp.route("/upload")
def upload_page():
    return render_template("upload.html")


@upload_bp.route("/api/upload", methods=["POST"])
def upload_video():
    try:
        if "video" not in request.files:
            return jsonify({"error": "No video file provided"}), 400

        video = request.files["video"]

        if video.filename == "":
            return jsonify({"error": "No file selected"}), 400

        if not allowed_file(video.filename):
            return jsonify({"error": f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

        upload_dir = current_app.config.get("UPLOAD_FOLDER", "uploads")
        os.makedirs(upload_dir, exist_ok=True)

        ext = video.filename.rsplit(".", 1)[1].lower()
        unique_name = f"upload_{uuid.uuid4().hex[:12]}.{ext}"
        filepath = os.path.join(upload_dir, unique_name)
        video.save(filepath)

        file_size = os.path.getsize(filepath)
        if file_size == 0:
            os.remove(filepath)
            return jsonify({"error": "Empty file uploaded"}), 400

        import cv2
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            os.remove(filepath)
            return jsonify({"error": "Unable to read video file"}), 400
        vfps = cap.get(cv2.CAP_PROP_FPS) or 0
        vframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        vdur = round(vframes / vfps, 1) if vfps > 0 else 0
        cap.release()

        camera_id = _assign_camera_id()

        _ensure_camera_exists(camera_id, video.filename, upload_dir)

        from backend.models.job import ProcessingJob
        job_count = ProcessingJob.query.count()
        job_id = f"JOB-{job_count + 1:05d}"

        job = ProcessingJob(
            job_id=job_id,
            camera_id=camera_id,
            video_path=filepath,
            video_filename=secure_filename(video.filename),
            video_fps=round(vfps, 2),
            video_width=vw,
            video_height=vh,
            video_duration=vdur,
            total_frames=vframes,
            status="QUEUED",
        )
        db.session.add(job)
        db.session.commit()

        logger.info(f"Upload received: {video.filename} ({file_size} bytes) -> {job_id} -> {camera_id}")

        socketio.emit("job_status_changed", {"jobId": job_id, "status": "QUEUED"})

        from backend.services.video_processor import process_video_job
        import threading
        thread = threading.Thread(
            target=process_video_job,
            args=(current_app._get_current_object(), job_id, filepath, camera_id),
            daemon=True,
        )
        thread.start()

        return jsonify({
            "success": True,
            "job_id": job_id,
            "camera_id": camera_id,
            "status": "QUEUED",
            "source": "uploaded_video",
            "filename": secure_filename(video.filename),
            "fileSize": file_size,
            "duration": vdur,
            "fps": round(vfps, 2),
            "resolution": f"{vw}x{vh}",
        }), 201

    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


@upload_bp.route("/api/upload/process-existing", methods=["POST"])
def process_existing_video():
    try:
        data = request.get_json()
        if not data or not data.get("filename"):
            return jsonify({"error": "filename is required"}), 400

        filename = secure_filename(data["filename"])
        upload_dir = current_app.config.get("UPLOAD_FOLDER", "uploads")
        filepath = os.path.join(upload_dir, filename)

        if not os.path.isfile(filepath):
            return jsonify({"error": f"File not found: {filename}"}), 404

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"error": f"Invalid file type: {ext}"}), 400

        import cv2
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            return jsonify({"error": "Unable to read video file"}), 400
        vfps = cap.get(cv2.CAP_PROP_FPS) or 0
        vframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        vdur = round(vframes / vfps, 1) if vfps > 0 else 0
        cap.release()

        from backend.models.job import ProcessingJob
        existing_job = ProcessingJob.query.filter_by(
            video_filename=filename, status="COMPLETED"
        ).first()
        if existing_job:
            return jsonify({
                "error": f"Video already processed as {existing_job.job_id}",
                "existing_job": existing_job.job_id,
            }), 409

        camera_id = _assign_camera_id()

        _ensure_camera_exists(camera_id, filename, upload_dir)

        job_count = ProcessingJob.query.count()
        job_id = f"JOB-{job_count + 1:05d}"

        job = ProcessingJob(
            job_id=job_id,
            camera_id=camera_id,
            video_path=filepath,
            video_filename=filename,
            video_fps=round(vfps, 2),
            video_width=vw,
            video_height=vh,
            video_duration=vdur,
            total_frames=vframes,
            status="QUEUED",
        )
        db.session.add(job)
        db.session.commit()

        logger.info(f"Processing existing video: {filename} -> {job_id} -> {camera_id}")

        socketio.emit("job_status_changed", {"jobId": job_id, "status": "QUEUED"})

        from backend.services.video_processor import process_video_job
        import threading
        thread = threading.Thread(
            target=process_video_job,
            args=(current_app._get_current_object(), job_id, filepath, camera_id),
            daemon=True,
        )
        thread.start()

        return jsonify({
            "success": True,
            "job_id": job_id,
            "camera_id": camera_id,
            "status": "QUEUED",
            "filename": filename,
            "duration": vdur,
            "fps": round(vfps, 2),
            "resolution": f"{vw}x{vh}",
        }), 201

    except Exception as e:
        logger.error(f"Process existing video failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def _ensure_camera_exists(camera_id, video_filename, upload_dir):
    from backend.models.camera import Camera
    existing = Camera.query.get(camera_id)
    if not existing:
        import cv2
        filepath = os.path.join(upload_dir, video_filename)
        fps_val = 25
        res = "1920x1080"
        try:
            cap = cv2.VideoCapture(filepath)
            if cap.isOpened():
                fps_val = int(cap.get(cv2.CAP_PROP_FPS) or 25)
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                res = f"{w}x{h}"
                cap.release()
        except Exception:
            pass

        cam = Camera(
            id=camera_id,
            name=f"Virtual Camera {camera_id}",
            zone="Recorded Video",
            status="online",
            fps=fps_val,
            resolution=res,
            source_path=filepath,
        )
        db.session.add(cam)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


@upload_bp.route("/api/jobs", methods=["GET"])
def get_jobs():
    try:
        from backend.models.job import ProcessingJob
        jobs = ProcessingJob.query.order_by(ProcessingJob.created_at.desc()).limit(50).all()
        return jsonify([j.to_dict() for j in jobs])
    except Exception as e:
        logger.error(f"Failed to load jobs: {e}")
        return jsonify([]), 200


@upload_bp.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    try:
        from backend.models.job import ProcessingJob
        job = ProcessingJob.query.filter_by(job_id=job_id).first()
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify(job.to_dict())
    except Exception as e:
        logger.error(f"Failed to load job {job_id}: {e}")
        return jsonify({"error": str(e)}), 500
