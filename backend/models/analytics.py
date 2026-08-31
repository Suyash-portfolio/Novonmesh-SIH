from datetime import datetime
from backend.extensions import db


class AnalyticsSnapshot(db.Model):
    __tablename__ = "analytics_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    snapshot_type = db.Column(db.String(30), nullable=False, index=True)
    camera_id = db.Column(db.String(20), nullable=True)
    hour_bucket = db.Column(db.Integer, nullable=True)
    date_bucket = db.Column(db.Date, nullable=True)
    vehicle_count = db.Column(db.Integer, default=0)
    unique_vehicles = db.Column(db.Integer, default=0)
    avg_speed = db.Column(db.Float, default=0.0)
    density = db.Column(db.Float, default=0.0)
    vehicle_class = db.Column(db.String(30), nullable=True)
    route_key = db.Column(db.String(255), nullable=True)
    extra_data = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.snapshot_type,
            "cameraId": self.camera_id,
            "hourBucket": self.hour_bucket,
            "dateBucket": self.date_bucket.isoformat() if self.date_bucket else None,
            "vehicleCount": self.vehicle_count,
            "uniqueVehicles": self.unique_vehicles,
            "avgSpeed": round(self.avg_speed, 1),
            "density": round(self.density, 1),
            "vehicleClass": self.vehicle_class,
            "routeKey": self.route_key,
            "extraData": self.extra_data,
        }
