import json

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from services import (
    ENERGY_QUESTION_COUNT,
    api_login_required,
    build_dashboard_state,
    format_user_name,
    generate_daily_plan,
    get_chat_history,
    get_current_time,
    get_current_user,
    get_db_connection,
    get_today_entry,
    get_today_string,
    login_required,
    normalize_task_list,
    parse_exercise_value,
)

onboarding_bp = Blueprint("onboarding", __name__)


@onboarding_bp.route("/")
@login_required
def home():
    if get_today_entry():
        return redirect(url_for("onboarding.dashboard"))

    return render_template(
        "onboarding.html",
        current_user_display=format_user_name(get_current_user()),
    )


@onboarding_bp.route("/dashboard")
@login_required
def dashboard():
    today_entry = get_today_entry()
    if not today_entry:
        return redirect(url_for("onboarding.home"))

    return render_template(
        "index.html",
        chat_history=get_chat_history(),
        today_entry=today_entry,
        dashboard_state=build_dashboard_state(today_entry),
        current_user_display=format_user_name(get_current_user()),
    )


@onboarding_bp.route("/dashboard_data", methods=["GET"])
@api_login_required
def dashboard_data():
    today_entry = get_today_entry()
    if not today_entry:
        return jsonify({"redirect_url": url_for("onboarding.home")}), 404

    return jsonify(build_dashboard_state(today_entry))


@onboarding_bp.route("/submit_day_data", methods=["POST"])
@api_login_required
def submit_day_data():
    # Save or replace today's setup in case the user re-submits before midnight.
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}

    tasks = normalize_task_list(data.get("tasks") or [])
    mood = (data.get("mood") or "").strip()
    exercised = parse_exercise_value(data.get("exercised"))

    try:
        sleep_hours = float(data.get("sleep_hours"))
    except (TypeError, ValueError):
        sleep_hours = None

    if not tasks:
        return jsonify({"error": "Please add at least one task for today."}), 400

    if sleep_hours is None or sleep_hours < 0 or sleep_hours > 24:
        return jsonify({"error": "Hours slept must be a number between 0 and 24."}), 400

    if mood not in {"Happy", "Normal", "Stressed"}:
        return jsonify({"error": "Please choose your mood for today."}), 400

    if exercised is None:
        return jsonify({"error": "Please choose whether you exercised today."}), 400

    plan = generate_daily_plan(tasks, sleep_hours, mood, exercised)
    entry_date = get_today_string()
    created_at = get_current_time().isoformat(timespec="seconds")
    existing_entry = get_today_entry()
    completed_tasks = []
    if existing_entry:
        completed_tasks = [
            task for task in existing_entry["completed_tasks"]
            if task in tasks
        ]

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO daily_entries (
            user,
            entry_date,
            tasks_json,
            sleep_hours,
            study_hours_total,
            mood,
            energy_level,
            exercised,
            plan,
            completed_tasks_json,
            energy_percent,
            energy_answers_json,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user, entry_date) DO UPDATE SET
            tasks_json = excluded.tasks_json,
            sleep_hours = excluded.sleep_hours,
            study_hours_total = daily_entries.study_hours_total,
            mood = excluded.mood,
            energy_level = excluded.energy_level,
            exercised = excluded.exercised,
            plan = excluded.plan,
            completed_tasks_json = excluded.completed_tasks_json,
            energy_percent = daily_entries.energy_percent,
            energy_answers_json = daily_entries.energy_answers_json,
            created_at = excluded.created_at
        """,
        (
            current_user,
            entry_date,
            json.dumps(tasks),
            sleep_hours,
            existing_entry["study_hours_total"] if existing_entry else 0,
            mood,
            0,
            int(exercised),
            plan,
            json.dumps(completed_tasks),
            existing_entry["energy_percent"] if existing_entry else 0,
            json.dumps(existing_entry["energy_answers"] if existing_entry else []),
            created_at,
        ),
    )
    conn.commit()
    conn.close()

    session["last_onboarding_date"] = entry_date

    return jsonify({
        "plan": plan,
        "redirect_url": url_for("onboarding.dashboard"),
    })


@onboarding_bp.route("/submit_energy", methods=["POST"])
@api_login_required
def submit_energy():
    # Energy can only be checked once per day so the bar stays consistent for that date.
    current_user = get_current_user()
    today_entry = get_today_entry()
    if not today_entry:
        return jsonify({"error": "Please complete today's setup first."}), 400

    if today_entry["energy_checked"]:
        return jsonify({"error": "Today's energy check has already been completed."}), 400

    data = request.get_json(silent=True) or {}
    answers = data.get("answers") or []

    if not isinstance(answers, list) or len(answers) != ENERGY_QUESTION_COUNT:
        return jsonify({"error": "Please answer all 10 energy questions."}), 400

    cleaned_answers = []
    total_score = 0
    for answer in answers:
        try:
            score = int(answer)
        except (TypeError, ValueError):
            score = None

        if score is None or score < 1 or score > 5:
            return jsonify({"error": "Each energy answer must be between 1 and 5."}), 400

        cleaned_answers.append(score)
        total_score += score

    energy_percent = round((total_score / (ENERGY_QUESTION_COUNT * 5)) * 100)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE daily_entries
        SET energy_percent = ?, energy_answers_json = ?
        WHERE user = ? AND entry_date = ?
        """,
        (energy_percent, json.dumps(cleaned_answers), current_user, today_entry["entry_date"]),
    )
    conn.commit()
    conn.close()

    return jsonify({
        "message": "Energy check saved.",
        "energy_percent": energy_percent,
        "dashboard_state": build_dashboard_state(get_today_entry()),
    })
