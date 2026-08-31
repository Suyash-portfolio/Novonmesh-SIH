from datetime import datetime
from backend.extensions import db


class BlacklistEntry(db.Model):
    __tablename__ = "blacklist"

    id = db.Column(db.Integer, primary_key=True)
    plate_text = db.Column(db.String(20), nullable=False, index=True)
    reason = db.Column(db.String(255), nullable=True)
    severity = db.Column(db.String(20), default="warning")
    is_active = db.Column(db.Boolean, default=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    added_by = db.Column(db.String(50), default="system")

    def to_dict(self):
        return {
            "id": self.id,
            "plateText": self.plate_text.upper(),
            "reason": self.reason or "",
            "severity": self.severity,
            "isActive": self.is_active,
            "expiresAt": self.expires_at.isoformat() if self.expires_at else None,
            "addedAt": self.added_at.isoformat() if self.added_at else None,
            "addedBy": self.added_by,
        }
