import os, sys, time, json
os.environ["FLASK_APP"] = "run.py"
os.environ["FLASK_ENV"] = "development"

upload_dir = "uploads"
processed_files = {"demo1.mp4"}

unprocessed = []
for f in sorted(os.listdir(upload_dir)):
    if f.endswith(".mp4") and f not in processed_files:
        path = os.path.join(upload_dir, f)
        size_mb = os.path.getsize(path) / (1024*1024)
        unprocessed.append((f, path, size_mb))
        print(f"  {f} ({size_mb:.1f}MB)")

print(f"\n{len(unprocessed)} unprocessed videos found")

from backend import create_app
app = create_app()

with app.app_context():
    import cv2
    from backend.extensions import db
    from backend.models.job import ProcessingJob
    from backend.models.camera import Camera
    from backend.routes.upload import _assign_camera_id, _ensure_camera_exists
    from backend.services.video_processor import process_video_job
    import threading

    for fname, fpath, fsize in unprocessed:
        cap = cv2.VideoCapture(fpath)
        if not cap.isOpened():
            print(f"  SKIP {fname}: cannot read")
            continue
        vfps = cap.get(cv2.CAP_PROP_FPS) or 0
        vframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        vdur = round(vframes / vfps, 1) if vfps > 0 else 0
        cap.release()

        existing = ProcessingJob.query.filter_by(video_filename=fname, status="COMPLETED").first()
        if existing:
            print(f"  SKIP {fname}: already processed as {existing.job_id}")
            continue

        camera_id = _assign_camera_id()
        _ensure_camera_exists(camera_id, fname, upload_dir)

        job_count = ProcessingJob.query.count()
        job_id = f"JOB-{job_count + 1:05d}"

        job = ProcessingJob(
            job_id=job_id,
            camera_id=camera_id,
            video_path=fpath,
            video_filename=fname,
            video_fps=round(vfps, 2),
            video_width=vw,
            video_height=vh,
            video_duration=vdur,
            total_frames=vframes,
            status="QUEUED",
        )
        db.session.add(job)
        db.session.commit()

        print(f"\nStarting {fname} -> {job_id} -> {camera_id}")
        thread = threading.Thread(
            target=process_video_job,
            args=(app._get_current_object(), job_id, fpath, camera_id),
            daemon=True,
        )
        thread.start()
        thread.join(timeout=600)

        job_check = ProcessingJob.query.filter_by(job_id=job_id).first()
        print(f"  Status: {job_check.status}")

    print("\nAll videos processed!")
    print(f"Total jobs: {ProcessingJob.query.count()}")
    for j in ProcessingJob.query.order_by(ProcessingJob.created_at).all():
        print(f"  {j.job_id}: {j.video_filename} -> {j.camera_id} ({j.status})")
