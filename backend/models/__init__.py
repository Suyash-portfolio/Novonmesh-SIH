from backend.extensions import db
from backend.models.camera import Camera
from backend.models.vehicle import Vehicle
from backend.models.detection import Detection
from backend.models.plate_read import PlateRead
from backend.models.sighting import VehicleSighting
from backend.models.transition import CameraTransition
from backend.models.trajectory import Trajectory
from backend.models.blacklist import BlacklistEntry
from backend.models.alert import Alert
from backend.models.analytics import AnalyticsSnapshot
from backend.models.job import ProcessingJob

__all__ = [
    "Camera", "Vehicle", "Detection", "PlateRead", "VehicleSighting",
    "CameraTransition", "Trajectory", "BlacklistEntry", "Alert",
    "AnalyticsSnapshot", "ProcessingJob",
]
