import logging
from flask import Blueprint, render_template

logger = logging.getLogger("navonmesh.dashboard")
dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    return render_template("dashboard.html")
