from flask import Blueprint, jsonify, request

from services import (
    WORKOUT_CALORIE_RATES,
    api_login_required,
    build_dashboard_state,
    get_current_time,
    get_current_user,
    get_db_connection,
    get_today_entry,
    get_today_string,
)

workout_bp = Blueprint("workout", __name__)


@workout_bp.route("/add_workout", methods=["POST"])
@api_login_required
def add_workout():
    current_user = get_current_user()
    today_entry = get_today_entry()
    if not today_entry:
        return jsonify({"error": "Please complete today's setup first."}), 400

    data = request.get_json(silent=True) or {}
    activity_type = (data.get("activity_type") or "").strip()

    try:
        duration = int(data.get("duration"))
    except (TypeError, ValueError):
        duration = None

    if activity_type not in WORKOUT_CALORIE_RATES:
        return jsonify({"error": "Please choose a valid workout type."}), 400

    if duration is None or duration <= 0 or duration > 300:
        return jsonify({"error": "Duration must be between 1 and 300 minutes."}), 400

    calories = duration * WORKOUT_CALORIE_RATES[activity_type]

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO workouts (
            user,
            entry_date,
            activity_type,
            duration,
            calories,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            current_user,
            get_today_string(),
            activity_type,
            duration,
            calories,
            get_current_time().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    conn.close()

    return jsonify(
        {
            "message": "Workout added.",
            "dashboard_state": build_dashboard_state(get_today_entry()),
        }
    )
