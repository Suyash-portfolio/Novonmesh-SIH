from datetime import datetime
from backend.extensions import db


class Detection(db.Model):
    __tablename__ = "detections"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("processing_jobs.id"), nullable=True)
    camera_id = db.Column(db.String(20), db.ForeignKey("cameras.id"), nullable=True, index=True)
    frame_index = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.Float, nullable=False)
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)
    bbox_x1 = db.Column(db.Float, nullable=False)
    bbox_y1 = db.Column(db.Float, nullable=False)
    bbox_x2 = db.Column(db.Float, nullable=False)
    bbox_y2 = db.Column(db.Float, nullable=False)
    vehicle_class = db.Column(db.String(30), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    vehicle_local_id = db.Column(db.Integer, nullable=True, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=True)
    crop_path = db.Column(db.String(255), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "cameraId": self.camera_id,
            "frameIndex": self.frame_index,
            "timestamp": self.timestamp,
            "detectedAt": self.detected_at.isoformat() if self.detected_at else None,
            "bbox": [self.bbox_x1, self.bbox_y1, self.bbox_x2, self.bbox_y2],
            "vehicleClass": self.vehicle_class,
            "confidence": round(self.confidence, 2),
            "vehicleLocalId": self.vehicle_local_id,
            "vehicleId": self.vehicle_id,
        }
