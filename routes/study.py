from flask import Blueprint, jsonify, request

from services import (
    api_login_required,
    build_dashboard_state,
    get_current_time,
    get_current_user,
    get_db_connection,
    get_today_entry,
    get_today_study_hours,
    set_study_hours_total,
    update_study_hours_total,
)

study_bp = Blueprint("study", __name__)


@study_bp.route("/add_study", methods=["POST"])
@api_login_required
def add_study():
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    subject = (data.get("subject") or "").strip()
    hours = data.get("hours")

    try:
        hours = float(hours)
    except (TypeError, ValueError):
        hours = None

    if not subject or not hours or hours <= 0:
        return jsonify({"error": "Missing data"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO study (subject, hours, created_at, user) VALUES (?, ?, ?, ?)",
        (subject, hours, get_current_time().isoformat(timespec="seconds"), current_user),
    )
    conn.commit()
    conn.close()

    try:
        updated_hours = min(24, get_today_study_hours(current_user) + hours)
        set_study_hours_total(updated_hours, current_user)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"message": "Study added"})


@study_bp.route("/get_study", methods=["GET"])
@api_login_required
def get_study():
    current_user = get_current_user()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM study WHERE user = ? ORDER BY id DESC", (current_user,))
    study_rows = cur.fetchall()
    conn.close()

    return jsonify(study_rows)


@study_bp.route("/log_study_progress", methods=["POST"])
@api_login_required
def log_study_progress():
    current_user = get_current_user()
    today_entry = get_today_entry()
    if not today_entry:
        return jsonify({"error": "Please complete today's setup first."}), 400

    data = request.get_json(silent=True) or {}
    subject = (data.get("subject") or "Focused session").strip() or "Focused session"

    try:
        hours = float(data.get("hours"))
    except (TypeError, ValueError):
        hours = None

    if hours is None or hours <= 0:
        return jsonify({"error": "Please enter valid study hours."}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO study (subject, hours, created_at, user) VALUES (?, ?, ?, ?)",
        (subject, hours, get_current_time().isoformat(timespec="seconds"), current_user),
    )
    conn.commit()
    conn.close()

    try:
        updated_hours = min(24, get_today_study_hours(current_user) + hours)
        set_study_hours_total(updated_hours, current_user)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "message": "Study progress updated.",
            "dashboard_state": build_dashboard_state(get_today_entry()),
        }
    )


@study_bp.route("/update_study", methods=["POST"])
@api_login_required
def update_study():
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").strip().lower()
    value = data.get("value")

    try:
        update_study_hours_total(action, value, get_current_user())
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "message": "Study hours updated.",
            "dashboard_state": build_dashboard_state(get_today_entry()),
        }
    )
