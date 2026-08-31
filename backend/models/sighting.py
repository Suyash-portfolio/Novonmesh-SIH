from datetime import datetime
from backend.extensions import db


class VehicleSighting(db.Model):
    __tablename__ = "vehicle_sightings"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    camera_id = db.Column(db.String(20), db.ForeignKey("cameras.id"), nullable=True, index=True)
    detection_id = db.Column(db.Integer, db.ForeignKey("detections.id"), nullable=True)
    local_track_id = db.Column(db.Integer, nullable=True)
    detected_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    direction = db.Column(db.String(50), nullable=True)
    speed = db.Column(db.Float, nullable=True)
    lane = db.Column(db.String(20), nullable=True)
    ocr_confidence = db.Column(db.Float, nullable=True)
    frame_index = db.Column(db.Integer, nullable=True)
    center_x = db.Column(db.Float, nullable=True)
    center_y = db.Column(db.Float, nullable=True)
    bbox_x1 = db.Column(db.Float, nullable=True)
    bbox_y1 = db.Column(db.Float, nullable=True)
    bbox_x2 = db.Column(db.Float, nullable=True)
    bbox_y2 = db.Column(db.Float, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "vehicleId": self.vehicle_id,
            "cameraId": self.camera_id,
            "cameraName": self.camera_id or "Unknown",
            "cameraZone": "",
            "detectedAt": self.detected_at.strftime("%H:%M:%S") if self.detected_at else "N/A",
            "direction": self.direction or "Unknown",
            "speed": round(self.speed, 1) if self.speed else 0,
            "lane": self.lane or "Unknown",
            "ocrConfidence": round(self.ocr_confidence, 1) if self.ocr_confidence else 0,
            "centerX": round(self.center_x, 1) if self.center_x is not None else None,
            "centerY": round(self.center_y, 1) if self.center_y is not None else None,
            "gapFromPrev": None,
            "distanceFromPrev": None,
        }
