from datetime import datetime
from backend.extensions import db


class Camera(db.Model):
    __tablename__ = "cameras"

    id = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    zone = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default="offline")
    lat = db.Column(db.Float, default=0.0)
    lng = db.Column(db.Float, default=0.0)
    map_x = db.Column(db.Float, default=0)
    map_y = db.Column(db.Float, default=0)
    fps = db.Column(db.Integer, default=25)
    resolution = db.Column(db.String(20), default="1920x1080")
    source_path = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    detections = db.relationship("Detection", backref="camera", lazy="dynamic")
    sightings = db.relationship("VehicleSighting", backref="camera", lazy="dynamic")

    def to_dict(self):
        from sqlalchemy import func
        from backend.models.detection import Detection

        try:
            vehicle_count = db.session.query(func.count(db.distinct(
                Detection.vehicle_local_id
            ))).filter(
                Detection.camera_id == self.id,
                Detection.vehicle_local_id.isnot(None)
            ).scalar() or 0
        except Exception:
            vehicle_count = 0

        try:
            recent_count = Detection.query.filter(
                Detection.camera_id == self.id,
                Detection.detected_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
            ).count()
        except Exception:
            recent_count = 0

        return {
            "id": self.id,
            "name": self.name,
            "zone": self.zone,
            "status": self.status,
            "lat": self.lat,
            "lng": self.lng,
            "x": self.map_x,
            "y": self.map_y,
            "fps": self.fps,
            "resolution": self.resolution,
            "vehicleCount": vehicle_count,
            "density": min(100, max(0, recent_count // 5)),
            "sourcePath": self.source_path,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
