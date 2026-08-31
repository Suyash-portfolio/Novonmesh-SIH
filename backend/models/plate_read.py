from datetime import datetime
from backend.extensions import db


class PlateRead(db.Model):
    __tablename__ = "plate_reads"

    id = db.Column(db.Integer, primary_key=True)
    detection_id = db.Column(db.Integer, db.ForeignKey("detections.id"), nullable=True)
    camera_id = db.Column(db.String(20), db.ForeignKey("cameras.id"), nullable=True, index=True)
    vehicle_local_id = db.Column(db.Integer, nullable=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=True, index=True)
    raw_text = db.Column(db.String(50), nullable=True)
    plate_text = db.Column(db.String(20), nullable=True, index=True)
    ocr_confidence = db.Column(db.Float, default=0.0)
    plate_bbox = db.Column(db.JSON, nullable=True)
    crop_path = db.Column(db.String(255), nullable=True)
    is_confirmed = db.Column(db.Boolean, default=False)
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "cameraId": self.camera_id,
            "rawText": self.raw_text,
            "plateText": self.plate_text,
            "ocrConfidence": round(self.ocr_confidence, 2),
            "isConfirmed": self.is_confirmed,
            "detectedAt": self.detected_at.isoformat() if self.detected_at else None,
        }
