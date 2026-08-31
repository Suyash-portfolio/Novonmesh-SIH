import logging
from flask import Blueprint, request, jsonify, render_template
from backend.extensions import db

logger = logging.getLogger("navonmesh.vehicles")
vehicles_bp = Blueprint("vehicles", __name__)


@vehicles_bp.route("/tracking")
def tracking_page():
    return render_template("tracking.html")


@vehicles_bp.route("/api/vehicles/search", methods=["GET"])
def search_vehicles():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    try:
        from backend.models.vehicle import Vehicle
        q_upper = q.upper().replace(" ", "")
        q_clean = q.strip()

        vehicle = Vehicle.query.filter(
            db.func.upper(Vehicle.plate_text) == q_upper
        ).first()

        if not vehicle:
            vehicle = Vehicle.query.filter(
                Vehicle.global_id.ilike(f"%{q_clean}%")
            ).first()

        if not vehicle:
            vehicle = Vehicle.query.filter(
                Vehicle.plate_text.ilike(f"%{q_clean}%")
            ).first()

        if not vehicle:
            return jsonify({"error": "No vehicle found", "query": q}), 404

        return jsonify(vehicle.to_dict())
    except Exception as e:
        logger.error(f"Vehicle search failed: {e}")
        return jsonify({"error": str(e)}), 500


@vehicles_bp.route("/api/vehicles", methods=["GET"])
def list_vehicles():
    try:
        from backend.models.vehicle import Vehicle
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 50, type=int)
        search = request.args.get("search", "").strip()

        query = Vehicle.query
        if search:
            query = query.filter(
                db.or_(
                    Vehicle.plate_text.ilike(f"%{search}%"),
                    Vehicle.global_id.ilike(f"%{search}%"),
                )
            )

        query = query.order_by(Vehicle.last_seen.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return jsonify({
            "vehicles": [v.to_dict() for v in pagination.items],
            "total": pagination.total,
            "page": page,
            "perPage": per_page,
        })
    except Exception as e:
        logger.error(f"Vehicle list failed: {e}")
        return jsonify({"vehicles": [], "total": 0, "page": 1, "perPage": 50}), 200


@vehicles_bp.route("/api/vehicles/<int:vehicle_id>", methods=["GET"])
def get_vehicle(vehicle_id):
    try:
        from backend.models.vehicle import Vehicle
        vehicle = Vehicle.query.get(vehicle_id)
        if not vehicle:
            return jsonify({"error": "Vehicle not found"}), 404
        return jsonify(vehicle.to_dict())
    except Exception as e:
        logger.error(f"Vehicle get failed: {e}")
        return jsonify({"error": str(e)}), 500


@vehicles_bp.route("/api/vehicles/<int:vehicle_id>", methods=["PUT"])
def update_vehicle(vehicle_id):
    try:
        from backend.models.vehicle import Vehicle
        vehicle = Vehicle.query.get(vehicle_id)
        if not vehicle:
            return jsonify({"error": "Vehicle not found"}), 404

        data = request.get_json()
        for field in ["vehicle_class", "color", "make", "model_name", "owner_state", "registration_year"]:
            if field in data:
                setattr(vehicle, field, data[field])
        if "watchlistStatus" in data:
            vehicle.watchlist_status = data["watchlistStatus"]

        db.session.commit()
        return jsonify(vehicle.to_dict())
    except Exception as e:
        logger.error(f"Vehicle update failed: {e}")
        return jsonify({"error": str(e)}), 500
