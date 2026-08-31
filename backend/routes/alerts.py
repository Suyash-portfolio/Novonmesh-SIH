import logging
from flask import Blueprint, render_template, jsonify, request
from backend.extensions import db

logger = logging.getLogger("navonmesh.alerts")
alerts_bp = Blueprint("alerts", __name__)


@alerts_bp.route("/alerts")
def alerts_page():
    return render_template("alerts.html")


@alerts_bp.route("/api/alerts", methods=["GET"])
def get_alerts():
    try:
        from backend.models.alert import Alert
        status = request.args.get("status")
        alert_type = request.args.get("type")
        limit = request.args.get("limit", 50, type=int)

        query = Alert.query.order_by(Alert.created_at.desc())
        if status:
            query = query.filter_by(status=status)
        if alert_type:
            query = query.filter_by(alert_type=alert_type)

        alerts = query.limit(limit).all()
        return jsonify([a.to_dict() for a in alerts])
    except Exception as e:
        logger.error(f"Failed to load alerts: {e}")
        return jsonify([]), 200


@alerts_bp.route("/api/alerts/<int:alert_id>", methods=["GET"])
def get_alert(alert_id):
    try:
        from backend.models.alert import Alert
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({"error": "Alert not found"}), 404
        return jsonify(alert.to_dict())
    except Exception as e:
        logger.error(f"Failed to load alert: {e}")
        return jsonify({"error": str(e)}), 500


@alerts_bp.route("/api/alerts/<int:alert_id>/acknowledge", methods=["PUT"])
def acknowledge_alert(alert_id):
    try:
        from backend.models.alert import Alert
        from datetime import datetime
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({"error": "Alert not found"}), 404
        alert.status = "acknowledged"
        alert.acknowledged_at = datetime.utcnow()
        db.session.commit()
        return jsonify(alert.to_dict())
    except Exception as e:
        logger.error(f"Failed to acknowledge alert: {e}")
        return jsonify({"error": str(e)}), 500


@alerts_bp.route("/api/alerts/<int:alert_id>/resolve", methods=["PUT"])
def resolve_alert(alert_id):
    try:
        from backend.models.alert import Alert
        from datetime import datetime
        alert = Alert.query.get(alert_id)
        if not alert:
            return jsonify({"error": "Alert not found"}), 404
        alert.status = "resolved"
        alert.resolved_at = datetime.utcnow()
        db.session.commit()
        return jsonify(alert.to_dict())
    except Exception as e:
        logger.error(f"Failed to resolve alert: {e}")
        return jsonify({"error": str(e)}), 500


@alerts_bp.route("/api/alerts/active-count", methods=["GET"])
def active_alert_count():
    try:
        from backend.models.alert import Alert
        count = Alert.query.filter_by(status="open").count()
        return jsonify({"count": count})
    except Exception as e:
        return jsonify({"count": 0}), 200
