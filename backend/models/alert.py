from datetime import datetime
from backend.extensions import db


class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)
    alert_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    alert_type = db.Column(db.String(30), nullable=False)
    severity = db.Column(db.String(20), default="info")
    plate_text = db.Column(db.String(20), nullable=True)
    camera_id = db.Column(db.String(20), nullable=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=True)
    detail = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="open")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        cam_str = self.camera_id or "N/A"
        if self.alert_type == "BLACKLIST":
            from backend.models.vehicle import Vehicle
            if self.vehicle_id:
                vehicle = Vehicle.query.get(self.vehicle_id)
                if vehicle:
                    from backend.models.sighting import VehicleSighting
                    sightings = VehicleSighting.query.filter_by(vehicle_id=self.vehicle_id).order_by(
                        VehicleSighting.detected_at.desc()
                    ).limit(2).all()
                    if len(sightings) >= 2:
                        cam_str = f"{sightings[1].camera_id} → {sightings[0].camera_id}"

        return {
            "id": self.id,
            "alertId": self.alert_id,
            "kind": self.alert_type,
            "severity": self.severity,
            "plate": self.plate_text or "N/A",
            "camera": cam_str,
            "time": self.created_at.strftime("%d %b, %H:%M:%S") if self.created_at else "N/A",
            "detail": self.detail or "",
            "status": self.status,
        }
