from datetime import datetime
from backend.extensions import db


class ProcessingJob(db.Model):
    __tablename__ = "processing_jobs"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    camera_id = db.Column(db.String(20), db.ForeignKey("cameras.id"), nullable=True)
    status = db.Column(db.String(20), default="QUEUED")
    video_path = db.Column(db.String(255), nullable=True)
    video_filename = db.Column(db.String(255), nullable=True)
    video_fps = db.Column(db.Float, nullable=True)
    video_width = db.Column(db.Integer, nullable=True)
    video_height = db.Column(db.Integer, nullable=True)
    video_duration = db.Column(db.Float, nullable=True)
    frames_processed = db.Column(db.Integer, default=0)
    total_frames = db.Column(db.Integer, default=0)
    vehicles_detected = db.Column(db.Integer, default=0)
    plates_detected = db.Column(db.Integer, default=0)
    ocr_successes = db.Column(db.Integer, default=0)
    output_video = db.Column(db.String(255), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    detections = db.relationship("Detection", backref="job", lazy="dynamic")

    def to_dict(self):
        annotated_filename = None
        if self.output_video:
            import os
            annotated_filename = os.path.basename(self.output_video)
        return {
            "id": self.id,
            "jobId": self.job_id,
            "cameraId": self.camera_id,
            "status": self.status,
            "videoFilename": self.video_filename,
            "videoFps": self.video_fps,
            "videoWidth": self.video_width,
            "videoHeight": self.video_height,
            "videoDuration": self.video_duration,
            "framesProcessed": self.frames_processed,
            "totalFrames": self.total_frames,
            "vehiclesDetected": self.vehicles_detected,
            "platesDetected": self.plates_detected,
            "ocrSuccesses": self.ocr_successes,
            "annotatedVideo": annotated_filename,
            "errorMessage": self.error_message,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "progress": round(
                (self.frames_processed / self.total_frames * 100) if self.total_frames > 0 else 0, 1
            ),
        }
