from datetime import datetime
from backend.extensions import db


class Vehicle(db.Model):
    __tablename__ = "vehicles"

    id = db.Column(db.Integer, primary_key=True)
    global_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    plate_text = db.Column(db.String(20), nullable=True, index=True)
    vehicle_class = db.Column(db.String(30), nullable=True)
    color = db.Column(db.String(30), nullable=True)
    make = db.Column(db.String(50), nullable=True)
    model_name = db.Column(db.String(50), nullable=True)
    registration_year = db.Column(db.Integer, nullable=True)
    owner_state = db.Column(db.String(30), nullable=True)
    watchlist_status = db.Column(db.String(20), default="clear")
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    avg_speed = db.Column(db.Float, default=0.0)
    total_distance = db.Column(db.Float, default=0.0)
    ocr_confidence = db.Column(db.Float, default=0.0)
    reid_embedding = db.Column(db.LargeBinary, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sightings = db.relationship("VehicleSighting", backref="vehicle", lazy="dynamic")
    transitions = db.relationship("CameraTransition", backref="vehicle", lazy="dynamic",
                                  foreign_keys="CameraTransition.vehicle_id")

    def to_dict(self):
        from backend.models.sighting import VehicleSighting as VS
        sightings = VS.query.filter_by(vehicle_id=self.id).order_by(
            VS.detected_at
        ).all()
        trail = [s.to_dict() for s in sightings]

        journey_duration = "N/A"
        if len(sightings) >= 2:
            delta = sightings[-1].detected_at - sightings[0].detected_at
            total_secs = int(delta.total_seconds())
            mins, secs = divmod(total_secs, 60)
            if mins > 0:
                journey_duration = f"{mins} min {secs} sec"
            else:
                journey_duration = f"{secs} sec"

        return {
            "id": self.id,
            "globalId": self.global_id,
            "plate": self.plate_text or "UNKNOWN",
            "type": self.vehicle_class or "Unknown",
            "make": self.make or "Unknown",
            "model": self.model_name or "",
            "color": self.color or "Unknown",
            "ownerState": self.owner_state or "Unknown",
            "registrationYear": self.registration_year,
            "watchlist": self.watchlist_status,
            "firstSeen": self.first_seen.strftime("%d %b %Y, %H:%M:%S") if self.first_seen else "N/A",
            "lastSeen": self.last_seen.strftime("%d %b %Y, %H:%M:%S") if self.last_seen else "N/A",
            "journeyDuration": journey_duration,
            "avgSpeed": round(self.avg_speed, 1),
            "totalDistance": round(self.total_distance, 1),
            "ocrConfidence": round(self.ocr_confidence, 1),
            "trail": trail,
            "cameraCount": len(set(s.camera_id for s in sightings)),
        }
