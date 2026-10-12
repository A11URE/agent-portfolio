"""Indicator warehouse routes — pre-built indicator library."""
from flask import Blueprint, jsonify, g, request

from app.utils.auth import login_required
from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)

warehouse_bp = Blueprint("warehouse", __name__)


@warehouse_bp.route("/indicator/warehouse/list", methods=["GET"])
@login_required
def list_warehouse():
    """List all warehouse indicators (without full code for performance)."""
    try:
        category = request.args.get("category", "")
        with get_db_connection() as conn:
            cur = conn.cursor()
            if category:
                cur.execute(
                    "SELECT id, name, description, category, sort_order "
                    "FROM qd_indicator_warehouse WHERE category=%s ORDER BY sort_order, id",
                    (category,)
                )
            else:
                cur.execute(
                    "SELECT id, name, description, category, sort_order "
                    "FROM qd_indicator_warehouse ORDER BY sort_order, id"
                )
            rows = cur.fetchall()
            cur.close()

        items = [
            {
                "id": r["id"], "name": r["name"], "description": r["description"],
                "category": r["category"], "sort_order": r["sort_order"],
            }
            for r in rows
        ]
        return jsonify({"code": 1, "msg": "success", "data": items})
    except Exception as e:
        return jsonify({"code": 0, "msg": str(e)}), 500


@warehouse_bp.route("/indicator/warehouse/<int:indicator_id>", methods=["GET"])
@login_required
def get_warehouse_indicator(indicator_id):
    """Get one warehouse indicator including full Python code."""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name, description, code, category "
                "FROM qd_indicator_warehouse WHERE id=%s",
                (indicator_id,)
            )
            row = cur.fetchone()
            cur.close()

        if not row:
            return jsonify({"code": 0, "msg": "Not found"}), 404

        return jsonify({
            "code": 1, "msg": "success",
            "data": {
                "id": row["id"], "name": row["name"],
                "description": row["description"], "code": row["code"],
                "category": row["category"],
            }
        })
    except Exception as e:
        return jsonify({"code": 0, "msg": str(e)}), 500
