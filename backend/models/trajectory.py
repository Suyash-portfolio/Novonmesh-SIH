from datetime import datetime
from backend.extensions import db


class Trajectory(db.Model):
    __tablename__ = "trajectories"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    total_distance_km = db.Column(db.Float, default=0.0)
    total_duration_seconds = db.Column(db.Float, default=0.0)
    avg_speed_kmh = db.Column(db.Float, default=0.0)
    camera_sequence = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vehicle = db.relationship("Vehicle", backref="trajectories")

    def to_dict(self):
        return {
            "id": self.id,
            "vehicleId": self.vehicle_id,
            "totalDistanceKm": round(self.total_distance_km, 2),
            "totalDurationSeconds": round(self.total_duration_seconds, 1),
            "avgSpeedKmh": round(self.avg_speed_kmh, 1),
            "cameraSequence": self.camera_sequence or [],
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
