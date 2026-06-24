import json
import hashlib
import importlib.util
import os
import secrets
import smtplib
import sqlite3
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path


REQUIREMENTS_FILE = Path(__file__).resolve().parent / "requirements.txt"


def ensure_runtime_dependencies():
    required_modules = {
        "flask": "flask",
        "dotenv": "python-dotenv",
        "flask_login": "flask-login",
    }
    missing_modules = [
        package_name
        for module_name, package_name in required_modules.items()
        if importlib.util.find_spec(module_name) is None
    ]

    if not missing_modules:
        return

    install_command = [sys.executable, "-m", "pip", "install"]
    if REQUIREMENTS_FILE.exists():
        install_command.extend(["-r", str(REQUIREMENTS_FILE)])
    else:
        install_command.extend(sorted(set(missing_modules)))

    print(
        f"Installing missing dependencies with: {' '.join(install_command)}",
        file=sys.stderr,
    )

    try:
        subprocess.check_call(install_command)
    except Exception as exc:  # pragma: no cover - depends on runtime environment
        raise RuntimeError(
            "Required Python dependencies are missing. If you are using a virtual environment, "
            "activate it first and rerun the app. Fallback: python -m pip install flask-login"
        ) from exc


ensure_runtime_dependencies()

from flask import Flask, flash, jsonify, redirect, request, session, url_for
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from config import (
    AI_MODEL,
    CAREER_STATUSES,
    DEFAULT_SECRET_KEY,
    ENERGY_QUESTION_COUNT,
    FLASK_CONFIG,
    MAX_CHAT_MESSAGES,
    STATIC_DIR,
    TEMPLATES_DIR,
    WORKOUT_CALORIE_RATES,
)
from database.db import get_db_connection, init_db
from utils.calculations import (
    build_health_guidance,
    calculate_health_insight,
    compute_streak_from_history,
    generate_daily_plan,
    generate_start_day_plan,
)
from utils.helpers import (
    api_login_required,
    configure_logging,
    format_progress_value,
    format_user_name,
    get_current_time,
    get_today_string,
    handle_uncaught_exception,
    login_required,
    normalize_career_text,
    normalize_date_history,
    normalize_priority,
    normalize_study_subjects,
    normalize_task_list,
    parse_exercise_value,
    parse_iso_date,
    prepare_runtime_paths,
    safe_render_template,
    set_app_logger,
)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - depends on deployment environment
    OpenAI = None

app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=str(STATIC_DIR),
    static_url_path="/static",
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.environ.get("SECRET_KEY") or DEFAULT_SECRET_KEY
app.config.update(SECRET_KEY=app.secret_key, **FLASK_CONFIG)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."
login_manager.init_app(app)


configure_logging(app)
set_app_logger(app.logger)
sys.excepthook = handle_uncaught_exception
prepare_runtime_paths(app.logger)

if not os.environ.get("GROQ_API_KEY"):
    app.logger.warning("GROQ_API_KEY is not set. AI routes will stay available but return safe fallback messages.")

if not os.environ.get("FLASK_SECRET_KEY") and not os.environ.get("SECRET_KEY"):
    app.logger.warning(
        "FLASK_SECRET_KEY is not set. Using a fixed development fallback secret; set a strong secret in production."
    )

CHAT_SESSIONS = {}
PENDING_AI_TASKS = {}


def get_ai_client():
    if OpenAI is None:
        raise RuntimeError("OpenAI SDK is not installed on the server.")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        app.logger.warning("GROQ_API_KEY is missing. AI features will return a safe fallback response.")
        raise RuntimeError("AI is not configured yet. Set GROQ_API_KEY on the server.")

    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )


@dataclass
class DashboardUser(UserMixin):
    id: str
    username: str
    email: str

    @classmethod
    def from_record(cls, record):
        return cls(
            id=str(record["id"]),
            username=record["username"],
            email=record["email"],
        )


def get_user_by_id(user_id):
    if not user_id:
        return None

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, email, password_hash FROM users WHERE id = ?",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "username": row[1],
        "email": row[2],
        "password_hash": row[3],
    }


@login_manager.user_loader
def load_user(user_id):
    record = get_user_by_id(user_id)
    if not record:
        return None
    return DashboardUser.from_record(record)


@app.before_request
def keep_session_alive():
    session.permanent = True

    if current_user.is_authenticated:
        try:
            session["user_id"] = int(current_user.get_id())
        except (TypeError, ValueError):
            session.pop("user_id", None)


def sign_in_user(user_record, remember=True):
    login_user(
        DashboardUser.from_record(user_record),
        remember=remember,
        duration=app.config["REMEMBER_COOKIE_DURATION"],
    )
    session["user_id"] = int(user_record["id"])
    session.permanent = True


def get_user_by_email(email):
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        return None

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, email, password_hash FROM users WHERE lower(email) = ?",
        (normalized_email,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "username": row[1],
        "email": row[2],
        "password_hash": row[3],
    }


def get_user_by_username(username):
    normalized_username = (username or "").strip().lower()
    if not normalized_username:
        return None

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, email, password_hash FROM users WHERE lower(username) = ?",
        (normalized_username,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "username": row[1],
        "email": row[2],
        "password_hash": row[3],
    }


def create_user_account(username, email, password):
    normalized_username = (username or "").strip()
    normalized_email = (email or "").strip().lower()
    password_text = password or ""

    if not normalized_username:
        raise ValueError("Username is required.")

    if not normalized_email:
        raise ValueError("Email is required.")

    if len(password_text) < 6:
        raise ValueError("Password must be at least 6 characters long.")

    if get_user_by_username(normalized_username):
        raise ValueError("That username is already taken.")

    if get_user_by_email(normalized_email):
        raise ValueError("That email is already registered.")

    password_hash = generate_password_hash(password_text)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (username, email, password_hash, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            normalized_username,
            normalized_email,
            password_hash,
            get_current_time().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()

    return user_id


def update_user_password(user_id, password):
    password_hash = generate_password_hash(password)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (password_hash, user_id),
    )
    conn.commit()
    conn.close()


def hash_reset_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def delete_reset_tokens_for_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def create_password_reset_token(user_id):
    token = secrets.token_urlsafe(32)
    token_hash = hash_reset_token(token)
    expires_at = get_current_time().timestamp() + 3600
    created_at = get_current_time().isoformat(timespec="seconds")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
    cur.execute(
        """
        INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, token_hash, expires_at, created_at),
    )
    conn.commit()
    conn.close()
    return token


def get_password_reset_user_id(token):
    token_hash = hash_reset_token(token)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, expires_at
        FROM password_reset_tokens
        WHERE token_hash = ?
        """,
        (token_hash,),
    )
    row = cur.fetchone()

    if not row:
        conn.close()
        return None, "invalid"

    user_id, expires_at = row
    if float(expires_at) < get_current_time().timestamp():
        cur.execute("DELETE FROM password_reset_tokens WHERE token_hash = ?", (token_hash,))
        conn.commit()
        conn.close()
        return None, "expired"

    conn.close()
    return user_id, None


def delete_password_reset_token(token):
    token_hash = hash_reset_token(token)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM password_reset_tokens WHERE token_hash = ?", (token_hash,))
    conn.commit()
    conn.close()


def send_password_reset_email(user, token):
    sender = os.environ.get("EMAIL_ADDRESS")
    password = os.environ.get("EMAIL_PASSWORD")
    if not sender or not password:
        raise RuntimeError("Email is not configured. Set EMAIL_ADDRESS and EMAIL_PASSWORD.")

    reset_link = url_for("reset_password", token=token, _external=True)
    message = EmailMessage()
    message["Subject"] = "Reset your Personal AI OS password"
    message["From"] = sender
    message["To"] = user["email"]
    message.set_content(
        "Hello,\n\n"
        "Use the link below to reset your Personal AI OS password. This link expires in 1 hour.\n\n"
        f"{reset_link}\n\n"
        "If you did not request this reset, you can ignore this email."
    )

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.starttls()
        smtp.login(sender, password)
        smtp.send_message(message)


def get_current_user_id():
    if current_user.is_authenticated:
        try:
            return int(current_user.get_id())
        except (TypeError, ValueError):
            return None

    try:
        return int(session.get("user_id"))
    except (TypeError, ValueError):
        return None


def get_current_user_record():
    return get_user_by_id(get_current_user_id())


def get_current_username():
    record = get_current_user_record()
    if not record:
        return None
    return record["username"]


def get_today_entry(user=None):
    # Keep one onboarding entry per calendar day so refreshes skip setup after completion.
    current_user = user or get_current_username()
    if not current_user:
        return None

    today = get_today_string()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
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
            calories_override,
            energy_answers_json
        FROM daily_entries
        WHERE user = ? AND entry_date = ? AND is_cleared = 0
        """,
        (current_user, today),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    try:
        tasks = json.loads(row[1])
    except json.JSONDecodeError:
        tasks = []
    try:
        completed_tasks = json.loads(row[8])
    except json.JSONDecodeError:
        completed_tasks = []
    try:
        energy_answers = json.loads(row[11])
    except json.JSONDecodeError:
        energy_answers = []

    cleaned_tasks = normalize_task_list(tasks if isinstance(tasks, list) else [])
    completed_task_set = set()
    if isinstance(completed_tasks, list):
        for task in completed_tasks:
            if isinstance(task, str) and task in cleaned_tasks:
                completed_task_set.add(task)

    return {
        "entry_date": row[0],
        "tasks": cleaned_tasks,
        "sleep_hours": row[2],
        "study_hours_total": row[3] or 0,
        "mood": row[4],
        "energy_level": row[5],
        "exercised": bool(row[6]),
        "plan": row[7],
        "completed_tasks": list(completed_task_set),
        "energy_percent": row[9] or 0,
        "calories_override": row[10],
        "energy_answers": energy_answers if isinstance(energy_answers, list) else [],
        "energy_checked": bool(energy_answers),
    }


def get_today_study_hours(user=None):
    today_entry = get_today_entry(user)
    if not today_entry:
        return 0
    return float(today_entry["study_hours_total"] or 0)


def get_today_workouts(user=None):
    current_user = user or get_current_username()
    if not current_user:
        return []

    # Keep every workout entry for the day so we can show a running activity log and calorie total.
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT activity_type, duration, calories
        FROM workouts
        WHERE user = ? AND entry_date = ? AND is_cleared = 0
        ORDER BY id DESC
        """,
        (current_user, get_today_string()),
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "activity_type": row[0],
            "duration": row[1],
            "calories": row[2],
        }
        for row in rows
    ]


def get_today_calories(user=None):
    today_entry = get_today_entry(user)
    if today_entry and today_entry.get("calories_override") is not None:
        return int(today_entry["calories_override"])
    workouts = get_today_workouts(user)
    return sum(int(item["calories"]) for item in workouts)


def get_today_exercise_minutes(user=None):
    workouts = get_today_workouts(user)
    return sum(int(item["duration"]) for item in workouts)


def get_today_user_lookup(user=None, user_id=None):
    return {
        "username": user or get_current_username(),
        "user_id": user_id or get_current_user_id(),
        "today": get_today_string(),
    }


def get_today_task_records(user=None):
    identity = get_today_user_lookup(user=user)
    if not identity["username"]:
        return []

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, priority, completed
        FROM tasks
        WHERE user = ? AND entry_date = ? AND task_type = 'daily' AND is_cleared = 0
        ORDER BY
            CASE priority
                WHEN 'High' THEN 1
                WHEN 'Medium' THEN 2
                ELSE 3
            END,
            id DESC
        """,
        (identity["username"], identity["today"]),
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "name": row[1],
            "priority": normalize_priority(row[2]),
            "completed": bool(row[3]),
            "type": "daily",
        }
        for row in rows
    ]


def get_long_term_task_records(user=None):
    identity = get_today_user_lookup(user=user)
    if not identity["username"]:
        return []

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, priority, streak_count, last_completed_date, completion_history_json
        FROM tasks
        WHERE user = ? AND task_type = 'long_term' AND is_cleared = 0
        ORDER BY
            CASE priority
                WHEN 'High' THEN 1
                WHEN 'Medium' THEN 2
                ELSE 3
            END,
            id DESC
        """,
        (identity["username"],),
    )
    rows = cur.fetchall()
    conn.close()

    tasks = []
    for row in rows:
        history = normalize_date_history(row[5])
        tasks.append(
            {
                "id": row[0],
                "name": row[1],
                "priority": normalize_priority(row[2]),
                "streak_count": compute_streak_from_history(history),
                "last_completed_date": row[4],
                "completed": identity["today"] in set(history),
                "type": "long_term",
            }
        )

    return tasks


def get_today_task_priority_lookup(user=None):
    lookup = {}
    for task in get_today_task_records(user):
        lookup.setdefault(task["name"], task["priority"])
    return lookup


def sync_today_task_records(task_names, user=None, priority_lookup=None, completed_lookup=None):
    identity = get_today_user_lookup(user=user)
    if not identity["username"]:
        return

    priority_lookup = priority_lookup or {}
    completed_lookup = set(completed_lookup or [])
    today = identity["today"]
    normalized_tasks = normalize_task_list(task_names)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name
        FROM tasks
        WHERE user = ? AND entry_date = ? AND task_type = 'daily' AND is_cleared = 0
        """,
        (identity["username"], today),
    )
    existing_rows = cur.fetchall()
    existing_lookup = {row[1]: row[0] for row in existing_rows}

    for task_name in normalized_tasks:
        if task_name in existing_lookup:
            cur.execute(
                """
                UPDATE tasks
                SET priority = ?, completed = ?, user_id = ?
                WHERE id = ?
                """,
                (
                    normalize_priority(priority_lookup.get(task_name)),
                    1 if task_name in completed_lookup else 0,
                    identity["user_id"],
                    existing_lookup[task_name],
                ),
            )
            continue

        cur.execute(
            """
            INSERT INTO tasks (
                name,
                user,
                user_id,
                entry_date,
                priority,
                task_type,
                completed,
                streak_count,
                completion_history_json,
                is_cleared,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 'daily', ?, 0, '[]', 0, ?)
            """,
            (
                task_name,
                identity["username"],
                identity["user_id"],
                today,
                normalize_priority(priority_lookup.get(task_name)),
                1 if task_name in completed_lookup else 0,
                get_current_time().isoformat(timespec="seconds"),
            ),
        )

    for existing_name, existing_id in existing_lookup.items():
        if existing_name not in normalized_tasks:
            cur.execute("UPDATE tasks SET is_cleared = 1 WHERE id = ?", (existing_id,))

    conn.commit()
    conn.close()


def add_user_task_from_ai(task_name, priority):
    current_user = get_current_username()
    current_user_id = get_current_user_id()
    today = get_today_string()
    cleaned_task_name = str(task_name or "").strip()
    normalized_priority = normalize_priority(priority)

    if not current_user or not current_user_id:
        raise RuntimeError("Please log in before adding tasks.")

    if not cleaned_task_name:
        raise ValueError("Task name is required.")

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT tasks_json
            FROM daily_entries
            WHERE user = ? AND entry_date = ? AND is_cleared = 0
            """,
            (current_user, today),
        )
        daily_entry_row = cur.fetchone()
        if not daily_entry_row:
            raise RuntimeError("Please complete today's setup first before adding tasks.")

        raw_tasks_json = daily_entry_row[0] or "[]"
        try:
            daily_tasks = json.loads(raw_tasks_json)
        except json.JSONDecodeError:
            daily_tasks = []

        daily_tasks = normalize_task_list(daily_tasks)
        existing_task_names = {item.casefold() for item in daily_tasks}
        if cleaned_task_name.casefold() in existing_task_names:
            return f"{cleaned_task_name} is already in your tasks."

        daily_tasks.append(cleaned_task_name)

        cur.execute(
            """
            UPDATE daily_entries
            SET tasks_json = ?
            WHERE user = ? AND entry_date = ? AND is_cleared = 0
            """,
            (json.dumps(daily_tasks), current_user, today),
        )

        cur.execute(
            """
            INSERT INTO tasks (
                name,
                user,
                user_id,
                entry_date,
                priority,
                task_type,
                completed,
                streak_count,
                completion_history_json,
                is_cleared,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 'daily', 0, 0, '[]', 0, ?)
            """,
            (
                cleaned_task_name,
                current_user,
                current_user_id,
                today,
                normalized_priority,
                get_current_time().isoformat(timespec="seconds"),
            ),
        )

        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        app.logger.exception("Failed to add a task from AI tool use.")
        raise RuntimeError("I couldn't add that task right now. Please try again.") from exc
    finally:
        conn.close()

    return f"I have added {cleaned_task_name} to your tasks!"


def save_energy_log(score, answers, user_id=None):
    current_user_id = user_id or get_current_user_id()
    if not current_user_id:
        raise RuntimeError("User session is missing.")

    timestamp = get_current_time().isoformat(timespec="seconds")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO energy_logs (user_id, score, entry_date, answers_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, entry_date) DO UPDATE SET
            score = excluded.score,
            answers_json = excluded.answers_json,
            updated_at = excluded.updated_at
        """,
        (
            current_user_id,
            score,
            get_today_string(),
            json.dumps(answers),
            timestamp,
            timestamp,
        ),
    )
    conn.commit()
    conn.close()


def get_latest_health_data(user_id=None):
    current_user_id = user_id or get_current_user_id()
    if not current_user_id:
        return None

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT height_cm, weight_kg, bmi, category, ideal_weight_min, ideal_weight_max, entry_date
        FROM health_data
        WHERE user_id = ?
        ORDER BY entry_date DESC, id DESC
        LIMIT 1
        """,
        (current_user_id,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return build_health_guidance({
        "height_cm": row[0],
        "weight_kg": row[1],
        "bmi": row[2],
        "category": row[3],
        "ideal_weight_min": row[4],
        "ideal_weight_max": row[5],
        "entry_date": row[6],
    })


def save_health_data(height_cm, weight_kg, user_id=None):
    current_user_id = user_id or get_current_user_id()
    if not current_user_id:
        raise RuntimeError("User session is missing.")

    insight = calculate_health_insight(height_cm, weight_kg)
    timestamp = get_current_time().isoformat(timespec="seconds")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO health_data (
            user_id,
            entry_date,
            height_cm,
            weight_kg,
            bmi,
            category,
            ideal_weight_min,
            ideal_weight_max,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, entry_date) DO UPDATE SET
            height_cm = excluded.height_cm,
            weight_kg = excluded.weight_kg,
            bmi = excluded.bmi,
            category = excluded.category,
            ideal_weight_min = excluded.ideal_weight_min,
            ideal_weight_max = excluded.ideal_weight_max,
            updated_at = excluded.updated_at
        """,
        (
            current_user_id,
            get_today_string(),
            insight["height_cm"],
            insight["weight_kg"],
            insight["bmi"],
            insight["category"],
            insight["ideal_weight_min"],
            insight["ideal_weight_max"],
            timestamp,
            timestamp,
        ),
    )
    conn.commit()
    conn.close()

    insight["entry_date"] = get_today_string()
    return insight


def build_dashboard_state(today_entry):
    sleep_goal = 8
    exercise_goal = 30
    calories_goal = 400
    exercise_minutes = get_today_exercise_minutes()
    current_user = get_current_username()
    career_study = get_career_study_snapshot(current_user)
    study_hours = float(career_study["today_hours"] or 0)
    study_goal = max(float(career_study["target_hours"] or 4), 0.5)
    subjects_studied_today = career_study["subjects_studied_today"]
    subject_catalog = get_career_subject_catalog(current_user)
    studied_lookup = {subject.casefold() for subject in subjects_studied_today}
    subjects_not_studied = [
        subject for subject in subject_catalog
        if subject.casefold() not in studied_lookup
    ]
    pipeline_entries = get_career_pipeline_entries(current_user)
    pipeline_focus = next(
        (
            entry for entry in pipeline_entries
            if str(entry.get("next_action") or "").strip() and entry.get("status") != "Completed"
        ),
        None,
    ) or next(
        (
            entry for entry in pipeline_entries
            if str(entry.get("next_action") or "").strip()
        ),
        {},
    )
    remaining_study_hours = max(study_goal - study_hours, 0)
    daily_tasks = get_today_task_records()
    if today_entry["tasks"] and not daily_tasks:
        sync_today_task_records(
            today_entry["tasks"],
            current_user,
            completed_lookup=today_entry["completed_tasks"],
        )
        daily_tasks = get_today_task_records()
    long_term_tasks = get_long_term_task_records()
    workouts = get_today_workouts()
    calories_burned = get_today_calories()
    health_data = get_latest_health_data()
    sleep_ratio = min(today_entry["sleep_hours"] / sleep_goal, 1.0)
    energy_percent = max(0, min(int(today_entry["energy_percent"]), 100))
    study_ratio = min(study_hours / study_goal, 1.0)
    exercise_ratio = min(exercise_minutes / exercise_goal, 1.0)
    calories_ratio = min(calories_burned / calories_goal, 1.0)

    completed_lookup = {task["name"] for task in daily_tasks if task["completed"]}
    total_tasks = len(daily_tasks)
    completed_tasks = sum(1 for task in daily_tasks if task["completed"])
    pending_tasks = [task["name"] for task in daily_tasks if not task["completed"]]
    task_ratio = (completed_tasks / total_tasks) if total_tasks else 0
    dynamic_plan = generate_daily_plan({
        "sleep_hours": today_entry["sleep_hours"],
        "energy_percent": energy_percent,
        "pending_tasks": pending_tasks,
        "completed_tasks": list(completed_lookup),
        "study_hours": study_hours,
        "exercise_minutes": exercise_minutes,
        "calories_burned": calories_burned,
        "current_hour": get_current_time().hour,
        "health": health_data,
        "pipeline_focus": pipeline_focus,
        "remaining_study_hours": remaining_study_hours,
        "subjects_not_studied": subjects_not_studied,
    })

    return {
        "entry_date": today_entry["entry_date"],
        "suggestions": dynamic_plan,
        "metrics": [
            {
                "key": "exercise",
                "emoji": "🧘",
                "label": "Exercise Ring",
                "value": f"{exercise_minutes} / {exercise_goal} mins",
                "percent": round(exercise_ratio * 100),
                "theme": "exercise",
            },
            {
                "key": "study",
                "emoji": "📚",
                "label": "Study Ring",
                "value": f"{format_progress_value(study_hours)} / {study_goal} hrs",
                "percent": round(study_ratio * 100),
                "theme": "study",
                "current_hours": study_hours,
                "target_hours": study_goal,
            },
            {
                "key": "tasks",
                "emoji": "🎯",
                "label": "Task Completion",
                "value": f"{completed_tasks} / {total_tasks} tasks done",
                "percent": round(task_ratio * 100),
                "theme": "tasks",
            },
            {
                "key": "calories",
                "emoji": "🔥",
                "label": "Calories Ring",
                "value": f"{calories_burned} / {calories_goal} kcal",
                "percent": round(calories_ratio * 100),
                "theme": "calories",
            },
        ],
        "bars": {
            "sleep": {
                "emoji": "😴",
                "label": "Sleep",
                "value": f"{format_progress_value(today_entry['sleep_hours'])} / {sleep_goal} hrs",
                "percent": round(sleep_ratio * 100),
            },
            "energy": {
                "emoji": "⚡",
                "label": "Energy",
                "value": f"{energy_percent}%",
                "percent": energy_percent,
                "checked": today_entry["energy_checked"],
            },
        },
        "energy_check": {
            "checked": bool(today_entry["energy_checked"]),
            "percent": energy_percent,
        },
        "study_form": {
            "default_subject": "Focused session",
        },
        "study_tracker": {
            **career_study,
            "subject_catalog": subject_catalog,
            "subjects_not_studied": subjects_not_studied,
        },
        "career_pipeline": pipeline_entries,
        "tasks": daily_tasks,
        "daily_tasks": daily_tasks,
        "long_term_tasks": long_term_tasks,
        "workouts": workouts,
        "workout_summary": {
            "total_calories": calories_burned,
            "goal_calories": calories_goal,
        },
        "health": health_data,
        "summary": {
            "sleep_hours": format_progress_value(today_entry["sleep_hours"]),
            "energy_percent": energy_percent,
            "exercise_minutes": exercise_minutes,
            "study_hours": format_progress_value(study_hours),
            "study_target_hours": format_progress_value(study_goal),
            "study_hours_remaining": format_progress_value(remaining_study_hours),
            "subjects_studied_today": subjects_studied_today,
            "subjects_studied_today_count": len(subjects_studied_today),
            "subjects_not_studied": subjects_not_studied,
            "pipeline_focus": pipeline_focus,
            "calories_burned": calories_burned,
            "completed_tasks": completed_tasks,
            "total_tasks": total_tasks,
            "pending_tasks": len(pending_tasks),
            "long_term_tasks": len(long_term_tasks),
        },
    }


def get_chat_history_key(user=None):
    current_user = user or get_current_username() or "guest"
    chat_session_id = get_chat_session_id()
    return f"{current_user}:{chat_session_id}"


def get_pending_ai_task(user=None):
    return PENDING_AI_TASKS.get(get_chat_history_key(user))


def set_pending_ai_task(task_name, priority, user=None):
    cleaned_task_name = str(task_name or "").strip()
    if not cleaned_task_name:
        return None

    pending_task = {
        "task_name": cleaned_task_name,
        "priority": normalize_priority(priority),
    }
    PENDING_AI_TASKS[get_chat_history_key(user)] = pending_task
    return pending_task


def clear_pending_ai_task(user=None):
    return PENDING_AI_TASKS.pop(get_chat_history_key(user), None)


def is_add_task_confirmation_message(message):
    normalized = str(message or "").strip().lower()
    return normalized in {
        "add this task",
        "yes, add task",
        "yes add task",
        "add it",
        "yes",
    }


def is_cancel_task_confirmation_message(message):
    normalized = str(message or "").strip().lower()
    return normalized in {
        "cancel",
        "cancel task",
        "don't add",
        "do not add",
        "no",
        "no thanks",
    }


def has_explicit_task_creation_intent(message):
    normalized = " ".join(str(message or "").strip().lower().split())
    if not normalized:
        return False

    intent_phrases = (
        "add this to task",
        "add this task",
        "create a task",
        "create task",
        "add reminder",
        "set a reminder",
        "remind me to",
    )
    return any(phrase in normalized for phrase in intent_phrases)


def get_career_pipeline_entries(user):
    if not user:
        return []

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, company_name, role, status, next_action
        FROM career_pipeline
        WHERE user = ?
        ORDER BY id DESC
        """,
        (user,),
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "company_name": row[1],
            "role": row[2],
            "status": row[3],
            "next_action": row[4],
        }
        for row in rows
    ]


def get_career_study_snapshot(user):
    if not user:
        return {
            "today_hours": 0,
            "weekly_total": 0,
            "target_hours": 4,
            "subjects_studied_today": [],
        }

    today = parse_iso_date(get_today_string()) or date.today()
    week_start = today - timedelta(days=today.weekday())

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(study_hours, 0), COALESCE(target_hours, 4), COALESCE(subjects_json, '[]')
        FROM career_study_tracker
        WHERE user = ? AND entry_date = ?
        """,
        (user, today.isoformat()),
    )
    today_row = cur.fetchone()
    cur.execute(
        """
        SELECT COALESCE(SUM(study_hours), 0)
        FROM career_study_tracker
        WHERE user = ? AND entry_date BETWEEN ? AND ?
        """,
        (user, week_start.isoformat(), today.isoformat()),
    )
    weekly_row = cur.fetchone()
    conn.close()

    subjects = []
    if today_row:
        try:
            subjects = normalize_study_subjects(json.loads(today_row[2] or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            subjects = []

    return {
        "today_hours": float(today_row[0] or 0) if today_row else 0,
        "weekly_total": float(weekly_row[0] or 0) if weekly_row else 0,
        "target_hours": float(today_row[1] or 4) if today_row else 4,
        "subjects_studied_today": subjects,
    }


def get_career_subject_catalog(user):
    if not user:
        return []

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT subject_name
        FROM career_subjects
        WHERE user = ?
        ORDER BY lower(subject_name)
        """,
        (user,),
    )
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows if row and row[0]]


def get_career_skill_focus(user):
    catalog = get_career_subject_catalog(user)
    studied_lookup = set(get_career_study_snapshot(user).get("subjects_studied_today") or [])
    return [
        {"subject_name": subject_name, "studied_today": subject_name in studied_lookup}
        for subject_name in catalog
    ]


def build_career_state(user):
    study_snapshot = get_career_study_snapshot(user)
    return {
        "pipeline_entries": get_career_pipeline_entries(user),
        "skill_focus": get_career_skill_focus(user),
        "study": {
            **study_snapshot,
            "subject_catalog": get_career_subject_catalog(user),
        },
    }


def add_career_pipeline_entry(user, company_name, role, status, next_action):
    if status not in CAREER_STATUSES:
        raise ValueError("Please choose a valid application status.")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO career_pipeline (
            user,
            company_name,
            role,
            status,
            next_action,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user,
            normalize_career_text(company_name, "Company name"),
            normalize_career_text(role, "Role"),
            status,
            normalize_career_text(next_action, "Next action"),
            get_current_time().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    conn.close()


def update_career_skill_focus(user, subjects_studied):
    snapshot = get_career_study_snapshot(user)
    save_career_study_hours(
        user,
        snapshot.get("today_hours", 0),
        snapshot.get("target_hours", 4),
        subjects_studied,
        get_career_subject_catalog(user),
    )


def save_career_study_hours(user, study_hours, target_hours=None, subjects_studied=None, subject_catalog=None):
    try:
        hours = float(study_hours)
    except (TypeError, ValueError):
        raise ValueError("Study hours must be a valid number.")

    if hours < 0 or hours > 24:
        raise ValueError("Study hours must be between 0 and 24.")

    try:
        target = float(target_hours if target_hours is not None else 4)
    except (TypeError, ValueError):
        raise ValueError("Target hours must be a valid number.")

    if target < 0.5 or target > 24:
        raise ValueError("Target hours must be between 0.5 and 24.")

    catalog = normalize_study_subjects(subject_catalog)
    if not catalog:
        catalog = get_career_subject_catalog(user)

    subjects = [
        subject
        for subject in normalize_study_subjects(subjects_studied)
        if subject in set(catalog)
    ]

    today = get_today_string()
    timestamp = get_current_time().isoformat(timespec="seconds")

    conn = get_db_connection()
    cur = conn.cursor()
    existing_subjects = {
        row[0]
        for row in cur.execute(
            "SELECT subject_name FROM career_subjects WHERE user = ?",
            (user,),
        ).fetchall()
    }

    for subject_name in catalog:
        cur.execute(
            """
            INSERT INTO career_subjects (user, subject_name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user, subject_name) DO UPDATE SET
                updated_at = excluded.updated_at
            """,
            (user, subject_name, timestamp, timestamp),
        )

    for subject_name in existing_subjects:
        if subject_name not in set(catalog):
            cur.execute(
                "DELETE FROM career_subjects WHERE user = ? AND subject_name = ?",
                (user, subject_name),
            )

    cur.execute(
        """
        INSERT INTO career_study_tracker (user, entry_date, study_hours, target_hours, subjects_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user, entry_date) DO UPDATE SET
            study_hours = excluded.study_hours,
            target_hours = excluded.target_hours,
            subjects_json = excluded.subjects_json,
            updated_at = excluded.updated_at
        """,
        (user, today, hours, target, json.dumps(subjects), timestamp),
    )
    conn.commit()
    conn.close()

init_db(app.logger)


@app.errorhandler(Exception)
def handle_application_error(error):
    if isinstance(error, HTTPException):
        return error

    app.logger.exception(
        "Unhandled exception during %s %s",
        request.method,
        request.path,
    )

    wants_json = request.is_json or request.path.startswith("/api") or request.accept_mimetypes.best == "application/json"
    if wants_json:
        return jsonify({"error": "Internal server error. Check server logs for details."}), 500

    return "Internal server error. Check Render logs for the traceback.", 500


def get_chat_session_id():
    chat_session_id = session.get("chat_session_id")
    if not chat_session_id:
        chat_session_id = str(uuid.uuid4())
        session["chat_session_id"] = chat_session_id
    return chat_session_id



def get_chat_history():
    return CHAT_SESSIONS.setdefault(get_chat_history_key(), [])



def trim_chat_history(history):
    if len(history) > MAX_CHAT_MESSAGES:
        del history[:-MAX_CHAT_MESSAGES]


def get_dashboard_context():
    current_user = get_current_username()
    today_entry = get_today_entry(current_user)
    workouts = get_today_workouts(current_user)
    long_term_tasks = get_long_term_task_records(current_user)
    health_data = get_latest_health_data()
    career_study = get_career_study_snapshot(current_user)
    pipeline_entries = get_career_pipeline_entries(current_user)
    subject_catalog = get_career_subject_catalog(current_user)

    if not current_user:
        return (
            "User Dashboard Data:\n"
            f"- Date: {get_today_string()}\n"
            "- Tasks Today: Not available yet\n"
            "- Pending Tasks: Not available yet\n"
            "- Completed Tasks: Not available yet\n"
            "- Study Goals: Not available yet\n"
            "- Habits: Not available yet\n"
            "- Activity Logs: Not available yet\n"
            "- Schedule: Not available yet\n"
            "- Long-Term Goals: Not available yet\n"
            "- Health Insight: Not available yet"
        )

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT name FROM tasks WHERE user = ? AND is_cleared = 0 ORDER BY id DESC LIMIT 8",
        (current_user,),
    )
    backlog_tasks = [row[0] for row in cur.fetchall()]

    cur.execute("SELECT habit, streak FROM habits WHERE user = ? ORDER BY id DESC LIMIT 8", (current_user,))
    habits = [{"name": row[0], "streak": row[1]} for row in cur.fetchall()]

    conn.close()

    tasks_today = today_entry["tasks"] if today_entry else []
    completed_today = today_entry["completed_tasks"] if today_entry else []
    completed_lookup = set(completed_today)
    pending_today = [task for task in tasks_today if task not in completed_lookup]
    habit_text = (
        ", ".join(f"{item['name']} (streak {item['streak']})" for item in habits)
        if habits else
        "No habits logged yet."
    )
    workout_text = (
        ", ".join(
            f"{item['activity_type']} for {item['duration']} min ({item['calories']} kcal)"
            for item in workouts[:5]
        )
        if workouts else
        "No activity logs today."
    )
    study_goal_text = (
        f"Target {format_progress_value(career_study['target_hours'])} hours today; "
        f"current progress {format_progress_value(career_study['today_hours'])} hour(s)."
    )
    schedule_text = "No schedule captured yet."

    if today_entry:
        schedule_text = today_entry["plan"] or "No schedule captured yet."

    tasks_today_text = ", ".join(tasks_today) if tasks_today else "No tasks planned for today yet."
    pending_text = ", ".join(pending_today) if pending_today else "No pending tasks right now."
    completed_text = ", ".join(completed_today) if completed_today else "No completed tasks yet."
    backlog_text = ", ".join(backlog_tasks) if backlog_tasks else "No backlog tasks saved."
    long_term_text = (
        ", ".join(f"{item['name']} (streak {item['streak_count']})" for item in long_term_tasks)
        if long_term_tasks else
        "No long-term goals yet."
    )
    health_text = (
        f"BMI {health_data['bmi']} ({health_data['category']}), ideal weight {health_data['ideal_weight_min']}-{health_data['ideal_weight_max']} kg."
        if health_data else
        "No health insight saved yet."
    )
    pipeline_text = (
        ", ".join(
            f"{entry['company_name']} - {entry['role']} ({entry['status']}, next: {entry['next_action']})"
            for entry in pipeline_entries[:3]
        )
        if pipeline_entries else
        "No active applications yet."
    )
    studied_today_text = (
        ", ".join(career_study["subjects_studied_today"])
        if career_study["subjects_studied_today"] else
        "No subjects marked today."
    )
    studied_lookup = {item.casefold() for item in career_study["subjects_studied_today"]}
    remaining_subjects = [
        subject for subject in subject_catalog
        if subject.casefold() not in studied_lookup
    ]
    remaining_subjects_text = ", ".join(remaining_subjects) if remaining_subjects else "All listed subjects were covered today."

    return (
        "User Dashboard Data:\n"
        f"- Date: {get_today_string()}\n"
        f"- Tasks Today: {tasks_today_text}\n"
        f"- Pending Tasks: {pending_text}\n"
        f"- Completed Tasks: {completed_text}\n"
        f"- Study Goals: {study_goal_text}\n"
        f"- Habits: {habit_text}\n"
        f"- Activity Logs: {workout_text}\n"
        f"- Schedule: {schedule_text}\n"
        f"- Career Pipeline: {pipeline_text}\n"
        f"- Study Subjects Today: {studied_today_text}\n"
        f"- Remaining Subjects: {remaining_subjects_text}\n"
        f"- Backlog Tasks: {backlog_text}\n"
        f"- Long-Term Goals: {long_term_text}\n"
        f"- Health Insight: {health_text}"
    )

def set_study_hours_total(hours, user=None):
    current_user = user or get_current_username()
    if not current_user:
        raise RuntimeError("User session is missing.")

    today_entry = get_today_entry(current_user)
    if not today_entry:
        raise RuntimeError("Please complete today's setup first.")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE daily_entries
        SET study_hours_total = ?
        WHERE user = ? AND entry_date = ?
        """,
        (hours, current_user, today_entry["entry_date"]),
    )
    conn.commit()
    conn.close()


def update_study_hours_total(action, value=None, user=None):
    current_user = user or get_current_username()
    if not current_user:
        raise RuntimeError("User session is missing.")

    # Study tracking now behaves like a single total for the current user and current date.
    today_entry = get_today_entry(current_user)
    if not today_entry:
        raise RuntimeError("Please complete today's setup first.")

    current_hours = float(today_entry["study_hours_total"] or 0)

    if action == "add":
        updated_hours = current_hours + 1
    elif action == "remove":
        updated_hours = max(0, current_hours - 1)
    elif action == "edit":
        try:
            updated_hours = float(value)
        except (TypeError, ValueError):
            raise ValueError("Please enter a valid study hour value.") from None
    elif action == "reset":
        updated_hours = 0
    else:
        raise ValueError("Invalid study update action.")

    if updated_hours < 0:
        raise ValueError("Study hours cannot be negative.")

    if updated_hours > 24:
        raise ValueError("Study hours cannot be more than 24.")

    set_study_hours_total(updated_hours, current_user)
    return updated_hours



def get_openai_reply(history, user_message, dashboard_context):
    explicit_task_intent = has_explicit_task_creation_intent(user_message)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a professional personal AI assistant. You help users plan their day, "
                "prioritize tasks, improve productivity, and give actionable advice based on their real data. "
                "Always give clear, structured, and practical suggestions. Keep responses concise, ideally within 8 to 10 lines. "
                "Use bullet points when helpful. If the dashboard data is sparse or missing, ask smart follow-up questions instead of saying you have no access. "
                "Never add tasks or ask task-confirmation questions unless the user explicitly asks to add a task, create a task, or add a reminder. "
                "When an idea could be useful as a task but the user did not ask to save it, respond normally and, if helpful, end with: "
                "'You can add this as a task if needed.'"
            ),
        },
        {"role": "system", "content": dashboard_context},
    ]

    for item in history:
        role = (item.get("role") or "").strip().lower()
        content = (item.get("content") or "").strip()
        if role in {"user", "assistant", "system"} and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})
    tools = [
        {
            "type": "function",
            "function": {
                "name": "add_user_task",
                "description": "Add a daily task for the current user only when the user explicitly asks to create a task or reminder.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_name": {
                            "type": "string",
                            "description": "The task to add to today's task list.",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["High", "Medium", "Low"],
                            "description": "Priority level for the task.",
                        },
                    },
                    "required": ["task_name", "priority"],
                    "additionalProperties": False,
                },
            },
        }
    ]

    request_options = {
        "model": AI_MODEL,
        "messages": messages,
    }
    if explicit_task_intent:
        request_options["tools"] = tools
        request_options["tool_choice"] = "auto"

    try:
        client = get_ai_client()
        response = client.chat.completions.create(**request_options)
    except Exception as exc:  # pragma: no cover - depends on live API/runtime
        app.logger.exception("AI chat request failed.")
        error_text = str(exc).lower()
        if "insufficient_quota" in error_text or "quota" in error_text:
            return "AI is temporarily unavailable. Please check API usage.", False, None
        if "not configured yet" in error_text or "groq_api_key" in error_text:
            raise RuntimeError("AI is not configured yet. Set GROQ_API_KEY on the server.") from exc
        raise RuntimeError("AI is temporarily unavailable. Please try again.") from exc

    assistant_message = response.choices[0].message if response.choices else None
    tool_calls = getattr(assistant_message, "tool_calls", None) or []
    if explicit_task_intent and tool_calls:
        for tool_call in tool_calls:
            function_name = getattr(getattr(tool_call, "function", None), "name", "")
            if function_name != "add_user_task":
                continue

            raw_arguments = getattr(tool_call.function, "arguments", "") or "{}"
            try:
                tool_arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                app.logger.warning("AI tool arguments could not be parsed: %s", raw_arguments)
                return "I had a task suggestion, but it could not be parsed correctly.", False, None

            if not isinstance(tool_arguments, dict):
                return "I had a task suggestion, but it could not be parsed correctly.", False, None

            task_name = str(tool_arguments.get("task_name") or "").strip()
            priority = str(tool_arguments.get("priority") or "").strip()
            try:
                bot_reply = add_user_task_from_ai(task_name, priority)
            except (RuntimeError, ValueError) as exc:
                return str(exc), False, None
            clear_pending_ai_task()
            return bot_reply, True, None

    response_text = (
        assistant_message.content.strip()
        if assistant_message and assistant_message.content
        else ""
    )

    if explicit_task_intent and not response_text:
        return "Tell me the exact task you'd like me to add.", False, None

    return response_text or "I could not generate a reply just now. Please try again.", False, None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = get_user_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            sign_in_user(user, remember=True)
            return redirect(url_for("home"))

        return safe_render_template("login.html", error="Invalid credentials")

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    return safe_render_template("login.html", error=None)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = get_user_by_email(email)

        if not user:
            return safe_render_template(
                "forgot_password.html",
                error="Email not found.",
                success=None,
                email=email,
            )

        token = create_password_reset_token(user["id"])
        try:
            send_password_reset_email(user, token)
        except RuntimeError as exc:
            delete_reset_tokens_for_user(user["id"])
            return safe_render_template(
                "forgot_password.html",
                error=str(exc),
                success=None,
                email=email,
            )
        except Exception:
            app.logger.exception("Password reset email failed for user id %s.", user["id"])
            delete_reset_tokens_for_user(user["id"])
            return safe_render_template(
                "forgot_password.html",
                error="Could not send reset email. Please try again later.",
                success=None,
                email=email,
            )

        return safe_render_template(
            "forgot_password.html",
            error=None,
            success="Password reset email sent. Please check your inbox.",
            email="",
        )

    return safe_render_template("forgot_password.html", error=None, success=None, email="")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user_id, token_error = get_password_reset_user_id(token)
    if token_error:
        message = "Expired token." if token_error == "expired" else "Invalid token."
        return safe_render_template(
            "reset_password.html",
            error=message,
            success=None,
            token_valid=False,
            token=token,
        )

    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not password:
            return safe_render_template(
                "reset_password.html",
                error="New password is required.",
                success=None,
                token_valid=True,
                token=token,
            )

        if len(password) < 6:
            return safe_render_template(
                "reset_password.html",
                error="Password must be at least 6 characters long.",
                success=None,
                token_valid=True,
                token=token,
            )

        if password != confirm_password:
            return safe_render_template(
                "reset_password.html",
                error="Password mismatch.",
                success=None,
                token_valid=True,
                token=token,
            )

        update_user_password(user_id, password)
        delete_password_reset_token(token)
        flash("Password updated successfully. Please log in.")
        return redirect(url_for("login"))

    return safe_render_template(
        "reset_password.html",
        error=None,
        success=None,
        token_valid=True,
        token=token,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        try:
            user_id = create_user_account(username, email, password)
        except ValueError as exc:
            return safe_render_template(
                "register.html",
                error=str(exc),
                form_data={"username": username, "email": email},
            )

        session.clear()
        user_record = get_user_by_id(user_id)
        if user_record:
            sign_in_user(user_record, remember=True)
        return redirect(url_for("home"))

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    return safe_render_template("register.html", error=None, form_data={"username": "", "email": ""})


@app.route("/logout", methods=["GET"])
@login_required
def logout():
    current_username = get_current_username() or "guest"
    app.logger.info("Logout route hit for user '%s'.", current_username)

    chat_session_id = session.pop("chat_session_id", None)
    if chat_session_id:
        CHAT_SESSIONS.pop(f"{current_username}:{chat_session_id}", None)
        PENDING_AI_TASKS.pop(f"{current_username}:{chat_session_id}", None)

    session.pop("user_id", None)
    logout_user()
    flash("Logged out successfully")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def home():
    if get_today_entry():
        return redirect(url_for("dashboard"))

    return safe_render_template(
        "onboarding.html",
        current_user_display=format_user_name(get_current_username()),
        day_notice="New day started. Ready to plan?" if request.args.get("day_reset") == "1" else None,
    )


@app.route("/dashboard")
@login_required
def dashboard():
    today_entry = get_today_entry()
    if not today_entry:
        return redirect(url_for("home"))
    career_study = get_career_study_snapshot(get_current_username())
    dashboard_state = build_dashboard_state(today_entry)

    return safe_render_template(
        "index.html",
        chat_history=get_chat_history(),
        today_entry=today_entry,
        dashboard_state=dashboard_state,
        subjects_studied_today=career_study["subjects_studied_today"],
        current_user_display=format_user_name(get_current_username()),
    )


@app.route("/career")
@login_required
def career():
    username = get_current_username()
    career_state = build_career_state(username)
    if request.args.get("partial") == "1":
        return safe_render_template(
            "components/career_content.html",
            username=username,
            career_state=career_state,
        )

    return safe_render_template(
        "career.html",
        username=username,
        career_state=career_state,
    )


@app.route("/financial")
@login_required
def financial():
    if request.args.get("partial") == "1":
        return safe_render_template("components/financial_content.html")

    return safe_render_template("financial.html")


@app.route("/career/add_application", methods=["POST"])
@api_login_required
def add_career_application():
    current_user = get_current_username()
    data = request.get_json(silent=True) or {}

    try:
        add_career_pipeline_entry(
            current_user,
            data.get("company_name"),
            data.get("role"),
            data.get("status"),
            data.get("next_action"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "message": "Application added.",
        "career_state": build_career_state(current_user),
    })


@app.route("/career/update_skills", methods=["POST"])
@api_login_required
def update_career_skills():
    current_user = get_current_username()
    data = request.get_json(silent=True) or {}

    try:
        update_career_skill_focus(current_user, data.get("subjects_studied") or [])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "message": "Skill progress updated.",
        "career_state": build_career_state(current_user),
    })


@app.route("/career/update_study", methods=["POST"])
@api_login_required
def update_career_study():
    current_user = get_current_username()
    data = request.get_json(silent=True) or {}

    try:
        save_career_study_hours(
            current_user,
            data.get("study_hours"),
            data.get("target_hours"),
            data.get("subjects_studied"),
            data.get("subject_catalog"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "message": "Study hours saved.",
        "career_state": build_career_state(current_user),
    })


@app.route("/add_task", methods=["POST"])
@api_login_required
def add_task():
    current_user = get_current_username()
    data = request.get_json(silent=True) or {}
    task = (data.get("task") or "").strip()
    priority = normalize_priority(data.get("priority"))
    task_type = (data.get("type") or "daily").strip().lower()

    if not task:
        return jsonify({"error": "Task is required."}), 400

    if task_type not in {"daily", "long_term"}:
        return jsonify({"error": "Unsupported task type."}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    if task_type == "daily":
        today_entry = get_today_entry(current_user)
        if not today_entry:
            conn.close()
            return jsonify({"error": "Please complete today's setup first."}), 400

        existing_lookup = {item.casefold() for item in today_entry["tasks"]}
        if task.casefold() in existing_lookup:
            conn.close()
            return jsonify({"error": "That task already exists for today."}), 400

        updated_tasks = today_entry["tasks"] + [task]
        cur.execute(
            """
            UPDATE daily_entries
            SET tasks_json = ?
            WHERE user = ? AND entry_date = ? AND is_cleared = 0
            """,
            (json.dumps(updated_tasks), current_user, today_entry["entry_date"]),
        )
        conn.commit()
        conn.close()

        priority_lookup = get_today_task_priority_lookup(current_user)
        priority_lookup[task] = priority
        sync_today_task_records(
            updated_tasks,
            current_user,
            priority_lookup,
            today_entry["completed_tasks"],
        )
    else:
        cur.execute(
            """
            SELECT id
            FROM tasks
            WHERE user = ? AND task_type = 'long_term' AND lower(name) = lower(?) AND is_cleared = 0
            """,
            (current_user, task),
        )
        if cur.fetchone():
            conn.close()
            return jsonify({"error": "That long-term goal already exists."}), 400

        cur.execute(
            """
            INSERT INTO tasks (
                name,
                user,
                user_id,
                entry_date,
                priority,
                task_type,
                completed,
                streak_count,
                last_completed_date,
                completion_history_json,
                is_cleared,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 'long_term', 0, 0, NULL, '[]', 0, ?)
            """,
            (
                task,
                current_user,
                get_current_user_id(),
                get_today_string(),
                priority,
                get_current_time().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        conn.close()

    return jsonify({
        "message": "Task added.",
        "dashboard_state": build_dashboard_state(get_today_entry(current_user)),
    })


@app.route("/tasks", methods=["GET"])
@api_login_required
def get_tasks():
    current_user = get_current_username()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, priority, entry_date, task_type, completed, streak_count, last_completed_date
        FROM tasks
        WHERE user = ? AND is_cleared = 0
        ORDER BY id DESC
        """,
        (current_user,),
    )
    rows = cur.fetchall()
    conn.close()

    tasks = [
        {
            "id": row[0],
            "name": row[1],
            "priority": row[2],
            "entry_date": row[3],
            "type": row[4],
            "completed": bool(row[5]),
            "streak_count": row[6] or 0,
            "last_completed_date": row[7],
        }
        for row in rows
    ]
    return jsonify(tasks)


@app.route("/delete_task/<int:task_id>", methods=["DELETE"])
@api_login_required
def delete_task(task_id):
    current_user = get_current_username()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, task_type, entry_date
            FROM tasks
            WHERE id = ? AND user = ? AND is_cleared = 0
            """,
            (task_id, current_user),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Task not found."}), 404

        _, task_name, task_type, entry_date = row

        cur.execute("UPDATE tasks SET is_cleared = 1 WHERE id = ? AND user = ?", (task_id, current_user))

        if task_type == "daily":
            cur.execute(
                """
                SELECT tasks_json, completed_tasks_json
                FROM daily_entries
                WHERE user = ? AND entry_date = ? AND is_cleared = 0
                """,
                (current_user, entry_date),
            )
            daily_entry_row = cur.fetchone()
            if daily_entry_row:
                try:
                    daily_tasks = json.loads(daily_entry_row[0] or "[]")
                except json.JSONDecodeError:
                    daily_tasks = []

                try:
                    completed_tasks = json.loads(daily_entry_row[1] or "[]")
                except json.JSONDecodeError:
                    completed_tasks = []

                normalized_name = str(task_name).casefold()
                updated_tasks = [
                    item for item in normalize_task_list(daily_tasks)
                    if str(item).casefold() != normalized_name
                ]
                updated_completed_tasks = [
                    item for item in normalize_task_list(completed_tasks)
                    if str(item).casefold() != normalized_name
                ]

                cur.execute(
                    """
                    UPDATE daily_entries
                    SET tasks_json = ?, completed_tasks_json = ?
                    WHERE user = ? AND entry_date = ? AND is_cleared = 0
                    """,
                    (
                        json.dumps(updated_tasks),
                        json.dumps(updated_completed_tasks),
                        current_user,
                        entry_date,
                    ),
                )

        conn.commit()
    finally:
        conn.close()

    today_entry = get_today_entry(current_user)
    dashboard_state = build_dashboard_state(today_entry) if today_entry else None

    return jsonify({
        "status": "deleted",
        "message": "Task deleted.",
        "dashboard_state": dashboard_state,
    })

@app.route("/add_habit", methods=["POST"])
@api_login_required
def add_habit():
    current_user = get_current_username()
    data = request.get_json(silent=True) or {}
    habit = (data.get("habit") or "").strip()

    if not habit:
        return jsonify({"error": "No habit provided"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO habits (habit, streak, user) VALUES (?, 0, ?)", (habit, current_user))
    conn.commit()
    conn.close()

    return jsonify({"message": "Habit added"})


@app.route("/get_habits", methods=["GET"])
@api_login_required
def get_habits():
    current_user = get_current_username()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM habits WHERE user = ? ORDER BY id DESC", (current_user,))
    data = cur.fetchall()
    conn.close()

    return jsonify(data)


@app.route("/update_streak/<int:habit_id>", methods=["POST"])
@api_login_required
def update_streak(habit_id):
    current_user = get_current_username()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE habits SET streak = streak + 1 WHERE id = ? AND user = ?", (habit_id, current_user))
    conn.commit()
    conn.close()

    return jsonify({"message": "Streak updated"})


@app.route("/get_stats", methods=["GET"])
@api_login_required
def get_stats():
    current_user = get_current_username()
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM tasks WHERE user = ?", (current_user,))
    total_tasks = cur.fetchone()[0]

    cur.execute("SELECT SUM(hours) FROM study WHERE user = ?", (current_user,))
    total_hours = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM habits WHERE user = ?", (current_user,))
    total_habits = cur.fetchone()[0]

    conn.close()

    return jsonify({
        "tasks": total_tasks,
        "study_hours": total_hours,
        "habits": total_habits
    })


@app.route("/dashboard_data", methods=["GET"])
@api_login_required
def dashboard_data():
    today_entry = get_today_entry()
    if not today_entry:
        return jsonify({"redirect_url": url_for("home")}), 404

    return jsonify(build_dashboard_state(today_entry))


@app.route("/log_study_progress", methods=["POST"])
@api_login_required
def log_study_progress():
    current_user = get_current_username()
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

    try:
        set_study_hours_total(min(24, get_today_study_hours(current_user) + hours), current_user)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "message": "Study progress updated.",
        "dashboard_state": build_dashboard_state(get_today_entry()),
    })


@app.route("/update_study", methods=["POST"])
@api_login_required
def update_study():
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").strip().lower()
    value = data.get("value")

    try:
        update_study_hours_total(action, value, get_current_username())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "message": "Study hours updated.",
        "dashboard_state": build_dashboard_state(get_today_entry()),
    })


@app.route("/update_day_metric", methods=["POST"])
@api_login_required
def update_day_metric():
    current_user = get_current_username()
    today_entry = get_today_entry(current_user)
    if not today_entry:
        return jsonify({"error": "Please complete today's setup first."}), 400

    data = request.get_json(silent=True) or {}
    metric = (data.get("metric") or "").strip().lower()
    value = data.get("value")

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        if metric == "sleep":
            numeric_value = float(value)
            if numeric_value < 0 or numeric_value > 24:
                raise ValueError("Sleep hours must be between 0 and 24.")
            cur.execute(
                "UPDATE daily_entries SET sleep_hours = ? WHERE user = ? AND entry_date = ? AND is_cleared = 0",
                (numeric_value, current_user, today_entry["entry_date"]),
            )
        elif metric == "energy":
            numeric_value = int(value)
            if numeric_value < 0 or numeric_value > 100:
                raise ValueError("Energy level must be between 0 and 100.")
            cur.execute(
                """
                UPDATE daily_entries
                SET energy_percent = ?, energy_level = ?, energy_answers_json = ?
                WHERE user = ? AND entry_date = ? AND is_cleared = 0
                """,
                (numeric_value, numeric_value, json.dumps([]), current_user, today_entry["entry_date"]),
            )
        elif metric == "calories":
            numeric_value = int(value)
            if numeric_value < 0 or numeric_value > 10000:
                raise ValueError("Calories must be between 0 and 10000.")
            cur.execute(
                "UPDATE daily_entries SET calories_override = ? WHERE user = ? AND entry_date = ? AND is_cleared = 0",
                (numeric_value, current_user, today_entry["entry_date"]),
            )
        else:
            raise ValueError("Unsupported metric update.")
    except (TypeError, ValueError) as exc:
        conn.close()
        return jsonify({"error": str(exc)}), 400

    conn.commit()
    conn.close()

    if metric == "energy":
        save_energy_log(int(numeric_value), [])

    return jsonify({
        "message": "Daily metric updated.",
        "dashboard_state": build_dashboard_state(get_today_entry(current_user)),
    })


@app.route("/reset_day", methods=["POST"])
@api_login_required
def reset_day():
    current_user = get_current_username()
    today = get_today_string()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE daily_entries SET is_cleared = 1 WHERE user = ? AND entry_date = ? AND is_cleared = 0",
        (current_user, today),
    )
    cur.execute(
        """
        UPDATE tasks
        SET is_cleared = 1
        WHERE user = ? AND entry_date = ? AND task_type = 'daily' AND is_cleared = 0
        """,
        (current_user, today),
    )
    cur.execute(
        "UPDATE workouts SET is_cleared = 1 WHERE user = ? AND entry_date = ? AND is_cleared = 0",
        (current_user, today),
    )
    conn.commit()
    conn.close()

    return jsonify({
        "message": "Day reset. New day started. Ready to plan?",
        "redirect_url": url_for("home", day_reset=1),
    })


@app.route("/add_workout", methods=["POST"])
@api_login_required
def add_workout():
    current_user = get_current_username()
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
            is_cleared,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            current_user,
            get_today_string(),
            activity_type,
            duration,
            calories,
            0,
            get_current_time().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    conn.close()

    return jsonify({
        "message": "Workout added.",
        "dashboard_state": build_dashboard_state(get_today_entry()),
    })


@app.route("/toggle_day_task", methods=["POST"])
@app.route("/toggle_task_status", methods=["POST"])
@api_login_required
def toggle_day_task():
    current_user = get_current_username()
    today_entry = get_today_entry()
    if not today_entry:
        return jsonify({"error": "Please complete today's setup first."}), 400

    data = request.get_json(silent=True) or {}
    task_name = (data.get("task_name") or "").strip()
    completed = bool(data.get("completed"))
    task_type = (data.get("type") or "daily").strip().lower()
    task_id = data.get("task_id")

    conn = get_db_connection()
    cur = conn.cursor()

    if task_type == "long_term":
        try:
            task_id = int(task_id)
        except (TypeError, ValueError):
            conn.close()
            return jsonify({"error": "Long-term task not found."}), 404

        cur.execute(
            """
            SELECT completion_history_json
            FROM tasks
            WHERE id = ? AND user = ? AND task_type = 'long_term' AND is_cleared = 0
            """,
            (task_id, current_user),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Long-term task not found."}), 404

        history = normalize_date_history(row[0])
        today = get_today_string()
        if completed and today not in history:
            history.append(today)
        if not completed and today in history:
            history.remove(today)
        history = normalize_date_history(history)
        streak_count = compute_streak_from_history(history)
        last_completed_date = history[-1] if history else None

        cur.execute(
            """
            UPDATE tasks
            SET completed = ?, streak_count = ?, last_completed_date = ?, completion_history_json = ?
            WHERE id = ?
            """,
            (
                1 if completed else 0,
                streak_count,
                last_completed_date,
                json.dumps(history),
                task_id,
            ),
        )
    else:
        if not task_name or task_name not in today_entry["tasks"]:
            conn.close()
            return jsonify({"error": "Task not found for today."}), 404

        completed_tasks = set(today_entry["completed_tasks"])
        if completed:
            completed_tasks.add(task_name)
        else:
            completed_tasks.discard(task_name)

        filtered_completed_tasks = [
            task for task in today_entry["tasks"]
            if task in completed_tasks
        ]

        cur.execute(
            """
            UPDATE daily_entries
            SET completed_tasks_json = ?
            WHERE user = ? AND entry_date = ?
            """,
            (json.dumps(filtered_completed_tasks), current_user, today_entry["entry_date"]),
        )
        cur.execute(
            """
            UPDATE tasks
            SET completed = ?
            WHERE user = ? AND entry_date = ? AND task_type = 'daily' AND name = ? AND is_cleared = 0
            """,
            (1 if completed else 0, current_user, today_entry["entry_date"], task_name),
        )

    conn.commit()
    conn.close()

    return jsonify({
        "message": "Task progress updated.",
        "dashboard_state": build_dashboard_state(get_today_entry()),
    })


@app.route("/submit_energy", methods=["POST"])
@api_login_required
def submit_energy():
    current_user = get_current_username()
    today_entry = get_today_entry()
    if not today_entry:
        return jsonify({"error": "Please complete today's setup first."}), 400

    data = request.get_json(silent=True) or {}
    answers = data.get("answers") or []

    if not isinstance(answers, list) or len(answers) != ENERGY_QUESTION_COUNT:
        return jsonify({"error": f"Please answer all {ENERGY_QUESTION_COUNT} energy questions."}), 400

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
        SET energy_percent = ?, energy_level = ?, energy_answers_json = ?
        WHERE user = ? AND entry_date = ?
        """,
        (energy_percent, energy_percent, json.dumps(cleaned_answers), current_user, today_entry["entry_date"]),
    )
    conn.commit()
    conn.close()
    save_energy_log(energy_percent, cleaned_answers)

    return jsonify({
        "message": "Energy recalculated.",
        "energy_percent": energy_percent,
        "dashboard_state": build_dashboard_state(get_today_entry()),
    })


@app.route("/submit_day_data", methods=["POST"])
@api_login_required
def submit_day_data():
    # Save or replace today's setup in case the user re-submits before midnight.
    current_user = get_current_username()
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

    if mood not in {"Focused", "Neutral", "Stressed", "Low Energy"}:
        return jsonify({"error": "Please choose your mood for today."}), 400

    if exercised is None:
        return jsonify({"error": "Please choose whether you exercised today."}), 400

    plan = generate_start_day_plan(tasks, sleep_hours, mood, exercised)
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
            calories_override,
            energy_answers_json,
            is_cleared,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user, entry_date) DO UPDATE SET
            tasks_json = excluded.tasks_json,
            sleep_hours = excluded.sleep_hours,
            study_hours_total = daily_entries.study_hours_total,
            mood = excluded.mood,
            energy_level = excluded.energy_level,
            exercised = excluded.exercised,
            plan = excluded.plan,
            completed_tasks_json = excluded.completed_tasks_json,
            energy_percent = excluded.energy_percent,
            calories_override = excluded.calories_override,
            energy_answers_json = excluded.energy_answers_json,
            is_cleared = excluded.is_cleared,
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
            existing_entry["calories_override"] if existing_entry else None,
            json.dumps(existing_entry["energy_answers"] if existing_entry else []),
            0,
            created_at,
        ),
    )
    conn.commit()
    conn.close()

    sync_today_task_records(tasks, current_user, completed_lookup=completed_tasks)

    session["last_onboarding_date"] = entry_date

    return jsonify({
        "plan": plan,
        "redirect_url": url_for("dashboard")
    })


@app.route("/analyze_health", methods=["POST"])
@api_login_required
def analyze_health():
    data = request.get_json(silent=True) or {}

    try:
        height_cm = float(data.get("height_cm"))
        weight_kg = float(data.get("weight_kg"))
    except (TypeError, ValueError):
        return jsonify({"error": "Height and weight must be valid numbers."}), 400

    if height_cm < 80 or height_cm > 250:
        return jsonify({"error": "Height should be between 80 cm and 250 cm."}), 400

    if weight_kg < 20 or weight_kg > 400:
        return jsonify({"error": "Weight should be between 20 kg and 400 kg."}), 400

    try:
        health_data = save_health_data(height_cm, weight_kg)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400

    today_entry = get_today_entry()
    dashboard_state = build_dashboard_state(today_entry) if today_entry else None

    return jsonify({
        "message": "Health insight updated.",
        "health": health_data,
        "dashboard_state": dashboard_state,
    })


@app.route("/chat", methods=["POST"])
@api_login_required
def chat():
    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()

    if not user_message:
        return jsonify({"error": "Message is required."}), 400

    history = get_chat_history()
    dashboard_context = get_dashboard_context()
    pending_task = get_pending_ai_task()

    if pending_task and is_add_task_confirmation_message(user_message):
        try:
            bot_reply = add_user_task_from_ai(
                pending_task["task_name"],
                pending_task["priority"],
            )
        except (RuntimeError, ValueError) as exc:
            bot_reply = str(exc)
        clear_pending_ai_task()
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": bot_reply})
        trim_chat_history(history)
        today_entry = get_today_entry()
        dashboard_state = build_dashboard_state(today_entry) if today_entry else None
        return jsonify({
            "response": bot_reply,
            "reply": bot_reply,
            "messages": history,
            "dashboard_state": dashboard_state,
            "tool_used": bool(dashboard_state),
            "pending_task": None,
        })

    if pending_task and is_cancel_task_confirmation_message(user_message):
        clear_pending_ai_task()
        bot_reply = "Okay, I won't add that task."
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": bot_reply})
        trim_chat_history(history)
        return jsonify({
            "response": bot_reply,
            "reply": bot_reply,
            "messages": history,
            "dashboard_state": None,
            "tool_used": False,
            "pending_task": None,
        })

    try:
        bot_reply, tool_used, pending_task = get_openai_reply(history, user_message, dashboard_context)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": bot_reply})
    trim_chat_history(history)
    today_entry = get_today_entry()
    dashboard_state = build_dashboard_state(today_entry) if tool_used and today_entry else None

    return jsonify({
        "response": bot_reply,
        "reply": bot_reply,
        "messages": history,
        "dashboard_state": dashboard_state,
        "tool_used": tool_used,
        "pending_task": pending_task,
    })


@app.route("/chat/confirm_task", methods=["POST"])
@api_login_required
def confirm_chat_task():
    pending_task = get_pending_ai_task()
    if not pending_task:
        return jsonify({"error": "No pending task suggestion found."}), 404

    try:
        bot_reply = add_user_task_from_ai(
            pending_task["task_name"],
            pending_task["priority"],
        )
    except (RuntimeError, ValueError) as exc:
        clear_pending_ai_task()
        return jsonify({"error": str(exc)}), 400

    clear_pending_ai_task()
    history = get_chat_history()
    history.append({"role": "assistant", "content": bot_reply})
    trim_chat_history(history)
    today_entry = get_today_entry()
    dashboard_state = build_dashboard_state(today_entry) if today_entry else None
    return jsonify({
        "message": bot_reply,
        "reply": bot_reply,
        "dashboard_state": dashboard_state,
        "pending_task": None,
    })


@app.route("/chat/cancel_task", methods=["POST"])
@api_login_required
def cancel_chat_task():
    pending_task = clear_pending_ai_task()
    if not pending_task:
        return jsonify({"error": "No pending task suggestion found."}), 404

    bot_reply = "Okay, I won't add that task."
    history = get_chat_history()
    history.append({"role": "assistant", "content": bot_reply})
    trim_chat_history(history)
    return jsonify({
        "message": bot_reply,
        "reply": bot_reply,
        "pending_task": None,
    })


@app.route("/ai-action", methods=["POST"])
def ai_action():
    try:
        data = request.get_json(silent=True) or {}
        user_message = (data.get("message") or "").strip()
        dashboard_context = get_dashboard_context()
        client = get_ai_client()

        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional personal AI assistant. You help users plan their day, "
                        "prioritize tasks, improve productivity, and give actionable advice based on their real data. "
                        "Always give clear, structured, and practical suggestions. Keep responses concise, ideally within 8 to 10 lines. "
                        "Use bullet points when helpful. If the dashboard data is sparse or missing, ask smart follow-up questions instead of saying you have no access."
                    ),
                },
                {"role": "system", "content": dashboard_context},
                {"role": "user", "content": user_message}
            ]
        )

        reply = response.choices[0].message.content

        return jsonify({"reply": reply})

    except Exception:  # pragma: no cover - depends on live API/runtime
        app.logger.exception("AI action request failed.")
        return jsonify({"reply": "AI is temporarily unavailable."})


# Debug startup for Render / Gunicorn
try:
    app.logger.info("Flask app initialized successfully.")
except Exception as e:
    import traceback
    print("STARTUP ERROR:", e)
    traceback.print_exc()
    raise


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 5000))
    app.logger.info("Starting local Flask development server on http://127.0.0.1:%s", port)
    print(f"Running locally on http://127.0.0.1:{port}")

    app.run(host="0.0.0.0", port=port, debug=True)
