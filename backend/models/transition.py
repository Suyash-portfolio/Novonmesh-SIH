from datetime import datetime
from backend.extensions import db


class CameraTransition(db.Model):
    __tablename__ = "camera_transitions"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    from_camera_id = db.Column(db.String(20), db.ForeignKey("cameras.id"), nullable=True)
    to_camera_id = db.Column(db.String(20), db.ForeignKey("cameras.id"), nullable=True)
    from_sighting_id = db.Column(db.Integer, db.ForeignKey("vehicle_sightings.id"), nullable=True)
    to_sighting_id = db.Column(db.Integer, db.ForeignKey("vehicle_sightings.id"), nullable=True)
    travel_time_seconds = db.Column(db.Float, nullable=True)
    estimated_distance_km = db.Column(db.Float, nullable=True)
    estimated_speed_kmh = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    from_camera = db.relationship("Camera", foreign_keys=[from_camera_id])
    to_camera = db.relationship("Camera", foreign_keys=[to_camera_id])

    def to_dict(self):
        return {
            "id": self.id,
            "vehicleId": self.vehicle_id,
            "fromCamera": self.from_camera_id,
            "toCamera": self.to_camera_id,
            "travelTimeSeconds": self.travel_time_seconds,
            "estimatedDistanceKm": self.estimated_distance_km,
            "estimatedSpeedKmh": self.estimated_speed_kmh,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
