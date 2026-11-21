import json
import hashlib
import hmac
import importlib.util
import os
import secrets
import smtplib
import sqlite3
import ssl
import subprocess
import sys
import uuid
from dataclasses import dataclass
from contextlib import closing
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


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
    normalize_priority,
    normalize_study_subjects,
    normalize_task_list,
    parse_exercise_value,
    parse_iso_date,
    prepare_runtime_paths,
    safe_render_template,
    set_app_logger,
)
import workspace_tasks as task_store

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
configured_secret_key = os.environ.get("FLASK_SECRET_KEY") or os.environ.get("SECRET_KEY")
if os.environ.get("RENDER") and (not configured_secret_key or configured_secret_key == DEFAULT_SECRET_KEY):
    raise RuntimeError("Set a stable FLASK_SECRET_KEY in Render before starting Personal AI OS.")
app.secret_key = configured_secret_key or DEFAULT_SECRET_KEY
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

if not configured_secret_key:
    app.logger.warning(
        "FLASK_SECRET_KEY is not set. Using a fixed development fallback secret; set a strong secret in production."
    )

CHAT_SESSIONS = {}
PENDING_AI_TASKS = {}
AUTH_FORM_ENDPOINTS = {"login", "register", "forgot_password", "reset_password", "change_password", "logout"}
TASK_FORM_ENDPOINTS = {"workspace_create_task", "workspace_edit_task", "workspace_set_task_status", "workspace_delete_task"}
TASK_PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
RESET_LINK_LIFETIME = timedelta(hours=1)
RESET_RESEND_INTERVAL = timedelta(minutes=1)


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
    login_identity: str

    @classmethod
    def from_record(cls, record):
        # Every password change invalidates the account's existing session and remember cookies.
        identity_data = f"{record['id']}:{record['password_hash']}".encode()
        signature = hmac.digest(app.secret_key.encode(), identity_data, "sha256").hex()
        return cls(
            id=str(record["id"]),
            username=record["username"],
            email=record["email"],
            login_identity=f"{record['id']}:{signature}",
        )

    def get_id(self):
        return self.login_identity


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
def load_user(identity):
    user_id, separator, _ = identity.partition(":")
    if not separator or not identity.isascii():
        return None
    record = get_user_by_id(user_id)
    if not record:
        return None
    user = DashboardUser.from_record(record)
    if secrets.compare_digest(user.get_id(), identity):
        return user
    return None


@app.template_global()
def auth_form_token():
    if "auth_form_token" not in session:
        session["auth_form_token"] = secrets.token_urlsafe(32)
    return session["auth_form_token"]


@app.before_request
def check_auth_form_token():
    if request.method != "POST" or request.endpoint not in AUTH_FORM_ENDPOINTS | TASK_FORM_ENDPOINTS:
        return None
    if request.endpoint in TASK_FORM_ENDPOINTS and not current_user.is_authenticated:
        return redirect(url_for("login"))
    expected = session.get("auth_form_token")
    submitted = request.form.get("auth_form_token", "").encode()
    if not expected or not secrets.compare_digest(expected.encode(), submitted):
        return safe_render_template(
            "auth_message.html",
            title="Form expired",
            message="Go back to the form, refresh it, and try again.",
        ), 400


@app.after_request
def set_auth_response_headers(response):
    if request.endpoint in AUTH_FORM_ENDPOINTS | TASK_FORM_ENDPOINTS | {"dashboard", "workspace_tasks"}:
        response.headers["Cache-Control"] = "no-store"
    if request.endpoint == "reset_password":
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


def sign_in_user(user_record, remember=False):
    session.clear()
    if not remember:
        # Flask-Login clears a remember cookie left over from a previous sign-in.
        logout_user()
    login_user(DashboardUser.from_record(user_record), remember=remember)


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


def update_user_password(user, password):
    password_hash = generate_password_hash(password)
    with closing(get_db_connection()) as conn, conn:
        updated = conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ? AND password_hash = ?",
            (password_hash, user["id"], user["password_hash"]),
        )
        if updated.rowcount != 1:
            return False
        conn.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user["id"],))
        return True


def hash_reset_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_password_reset_token(user_id):
    token = secrets.token_urlsafe(32)
    now = get_current_time()
    expires_at = now + RESET_LINK_LIFETIME

    with closing(get_db_connection()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        recently_requested = conn.execute(
            "SELECT 1 FROM password_reset_tokens WHERE user_id = ? AND expires_at > ?",
            (user_id, (expires_at - RESET_RESEND_INTERVAL).timestamp()),
        ).fetchone()
        if recently_requested:
            return None
        conn.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
        conn.execute(
            """
            INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, hash_reset_token(token), expires_at.timestamp(), now.isoformat(timespec="seconds")),
        )
    return token


def get_password_reset_user(token):
    with closing(get_db_connection()) as conn:
        return conn.execute(
            """
            SELECT users.id, users.email
            FROM password_reset_tokens JOIN users ON users.id = password_reset_tokens.user_id
            WHERE token_hash = ? AND expires_at > ?
            """,
            (hash_reset_token(token), get_current_time().timestamp()),
        ).fetchone()


def reset_user_password(user_id, token, password):
    password_hash = generate_password_hash(password)
    with closing(get_db_connection()) as conn, conn:
        consumed = conn.execute(
            "DELETE FROM password_reset_tokens WHERE user_id = ? AND token_hash = ? AND expires_at > ?",
            (user_id, hash_reset_token(token), get_current_time().timestamp()),
        )
        if consumed.rowcount != 1:
            return False
        updated = conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        return updated.rowcount == 1


def get_password_reset_origin():
    configured_origin = os.environ.get("APP_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    try:
        parsed = urlsplit(configured_origin or request.host_url)
        parsed.port  # Validate that an explicitly supplied port is usable.
    except ValueError:
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        return None
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"} and not os.environ.get("RENDER")
    if not parsed.hostname or not (configured_origin or local):
        return None
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def send_password_reset_email(email, reset_link):
    subject = "Reset your Personal AI OS password"
    body = (
        "Use the link below to reset your Personal AI OS password. This link expires in 1 hour.\n\n"
        f"{reset_link}\n\n"
        "If you did not request this reset, you can ignore this email."
    )
    api_key = os.environ.get("RESEND_API_KEY")
    reset_sender = os.environ.get("PASSWORD_RESET_FROM")
    if api_key and reset_sender:
        email_request = Request(
            "https://api.resend.com/emails",
            data=json.dumps({"from": reset_sender, "to": [email], "subject": subject, "text": body}).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(email_request, timeout=8):
            return

    sender = os.environ.get("EMAIL_ADDRESS")
    password = os.environ.get("EMAIL_PASSWORD")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = email
    message.set_content(body)

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=8) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(sender, password)
        smtp.send_message(message)


def get_current_user_id():
    if current_user.is_authenticated:
        return int(current_user.id)
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


def get_today_task_records():
    today = get_current_time().date()
    tasks = task_store.list_tasks(
        get_current_user_id(), current_user.username, today=today, task_type="daily", entry_date=today,
    )
    return [
        {
            "id": task["id"],
            "name": task["title"],
            "priority": task["priority"],
            "completed": task["completed"],
            "type": "daily",
        }
        for task in sorted(tasks, key=lambda task: TASK_PRIORITY_ORDER[task["priority"]])
    ]


def get_long_term_task_records():
    if not current_user.is_authenticated:
        return []
    tasks = task_store.list_tasks(
        get_current_user_id(), current_user.username, today=get_current_time().date(), task_type="long_term",
    )
    return [
        {
            "id": task["id"],
            "name": task["title"],
            "priority": task["priority"],
            "completed": task["completed"],
            "streak_count": task["streak_count"],
            "last_completed_date": task["last_completed_date"],
            "type": "long_term",
        }
        for task in sorted(tasks, key=lambda task: TASK_PRIORITY_ORDER[task["priority"]])
    ]


def add_user_task_from_ai(task_name, priority):
    user_id = get_current_user_id()
    if not user_id:
        raise RuntimeError("Please log in before adding tasks.")
    title = str(task_name or "").strip()
    try:
        task_store.create_task(
            user_id, current_user.username, title=title, priority=normalize_priority(priority),
            timestamp=get_current_time(),
        )
    except sqlite3.Error as error:
        app.logger.exception("Failed to add a task from AI tool use.")
        raise RuntimeError("I couldn't add that task right now. Please try again.") from error
    return f"I have added {title} to your tasks!"


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
    long_term_tasks = get_long_term_task_records()
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

    backlog_tasks = [
        task["title"]
        for task in task_store.list_tasks(get_current_user_id(), current_user, today=get_current_time().date(), limit=8)
    ]

    conn = get_db_connection()
    cur = conn.cursor()
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
    email = ""
    remember = True
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        remember = request.form.get("remember") == "on"

        user = get_user_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            sign_in_user(user, remember=remember)
            return redirect(url_for("home"))
        error = "The email or password is incorrect."
    elif current_user.is_authenticated:
        return redirect(url_for("home"))

    return safe_render_template("login.html", email=email, remember=remember, error=error)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return safe_render_template("forgot_password.html", email="")

    email = (request.form.get("email") or "").strip().lower()
    origin = get_password_reset_origin()
    resend_configured = os.environ.get("RESEND_API_KEY") and os.environ.get("PASSWORD_RESET_FROM")
    smtp_configured = os.environ.get("EMAIL_ADDRESS") and os.environ.get("EMAIL_PASSWORD")
    if not origin or not (resend_configured or smtp_configured):
        return safe_render_template(
            "forgot_password.html",
            error="Password reset email is temporarily unavailable.",
            email=email,
        ), 503

    user = get_user_by_email(email)
    if user:
        token = create_password_reset_token(user["id"])
        if token:
            reset_link = origin + url_for("reset_password", token=token)
            try:
                send_password_reset_email(user["email"], reset_link)
            except (OSError, ValueError):
                app.logger.exception("Password reset email failed for user id %s.", user["id"])

    flash("If an account uses that email address, you’ll receive a reset link. Check your spam folder if it doesn’t arrive.")
    return redirect(url_for("forgot_password"))


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = get_password_reset_user(token)
    if not user:
        return safe_render_template(
            "auth_message.html",
            title="Reset link unavailable",
            message="This link has expired or has already been used.",
            retry_reset=True,
        ), 400

    user_id, email = user
    error = None
    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""
        if len(password) < 6:
            error = "Use at least 6 characters."
        elif password != confirm_password:
            error = "The passwords do not match."
        elif reset_user_password(user_id, token, password):
            session.clear()
            logout_user()
            flash("Password updated. Sign in with your new password.")
            return redirect(url_for("login"))
        else:
            return redirect(url_for("reset_password", token=token))

    return safe_render_template("reset_password.html", token=token, email=email, error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    remember = True
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        remember = request.form.get("remember") == "on"

        try:
            user_id = create_user_account(username, email, password)
        except ValueError as exc:
            return safe_render_template(
                "register.html",
                error=str(exc),
                remember=remember,
                form_data={"username": username, "email": email},
            )

        user_record = get_user_by_id(user_id)
        if user_record:
            sign_in_user(user_record, remember=remember)
        return redirect(url_for("home"))

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    return safe_render_template("register.html", remember=remember, form_data={"username": "", "email": ""})


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    error = None
    if request.method == "POST":
        user = get_current_user_record()
        current_password = request.form.get("current_password") or ""
        password = request.form.get("new_password") or ""
        confirmation = request.form.get("confirm_password") or ""
        if not check_password_hash(user["password_hash"], current_password):
            error = "The current password is incorrect."
        elif len(password) < 6:
            error = "Use at least 6 characters."
        elif password != confirmation:
            error = "The passwords do not match."
        elif update_user_password(user, password):
            session.clear()
            logout_user()
            flash("Password updated. Sign in with your new password.")
            return redirect(url_for("login"))
        else:
            return redirect(url_for("login"))
    return safe_render_template("change_password.html", error=error)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    current_username = get_current_username() or "guest"
    app.logger.info("Logout route hit for user '%s'.", current_username)

    chat_session_id = session.pop("chat_session_id", None)
    if chat_session_id:
        CHAT_SESSIONS.pop(f"{current_username}:{chat_session_id}", None)
        PENDING_AI_TASKS.pop(f"{current_username}:{chat_session_id}", None)

    session.clear()
    logout_user()
    flash("Logged out successfully")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def home():
    return redirect(url_for("dashboard"))


@app.get("/daily-setup")
@login_required
def daily_setup():
    return safe_render_template(
        "onboarding.html",
        current_user_display=format_user_name(get_current_username()),
        day_notice="Update your daily setup. Your tasks and workouts are saved." if request.args.get("day_reset") == "1" else None,
    )


@app.route("/dashboard")
@login_required
def dashboard():
    if request.args.get("legacy") == "1" or request.args.get("page") == "activity" or request.args.get("open_ai") == "1":
        return render_legacy_dashboard()

    today = get_current_time().date()
    tasks = task_store.list_tasks(get_current_user_id(), current_user.username, today=today)
    open_tasks = [task for task in tasks if not task["completed"]]
    today_tasks = [
        task for task in open_tasks
        if (task["due_date"] and task["due_date"] <= today)
        or (not task["due_date"] and task["task_type"] == "daily" and task["entry_date"] == today)
    ]
    today_tasks.sort(key=lambda task: (
        not (task["due_date"] and task["due_date"] < today),
        TASK_PRIORITY_ORDER[task["priority"]],
        task["due_date"] or today,
        task["id"],
    ))
    upcoming_tasks = sorted(
        (task for task in open_tasks if task["due_date"] and task["due_date"] > today),
        key=lambda task: (task["due_date"], TASK_PRIORITY_ORDER[task["priority"]], task["id"]),
    )
    return safe_render_template(
        "workspace/today.html",
        active_page="today",
        display_name=current_user.username,
        today=today,
        next_task=today_tasks[0] if today_tasks else None,
        priority_tasks=today_tasks[1:],
        upcoming_tasks=upcoming_tasks,
    )


def render_legacy_dashboard():
    today_entry = get_today_entry()
    if not today_entry:
        return redirect(url_for("daily_setup"))
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


def render_workspace_tasks(*, editing_task=None, form_values=None, form_error=None, return_to="tasks"):
    today = get_current_time().date()
    tasks = [] if editing_task else task_store.list_tasks(get_current_user_id(), current_user.username, today=today)
    return safe_render_template(
        "workspace/tasks.html",
        active_page="edit" if editing_task else "tasks",
        display_name=current_user.username,
        today=today,
        tasks=tasks,
        editing_task=editing_task,
        form_values=form_values or {},
        form_error=form_error,
        return_to=return_to,
    )


def task_form_values():
    return {name: request.form.get(name, "") for name in ("title", "priority", "due_date")}


def redirect_after_task_change():
    destination = "dashboard" if request.form.get("return_to") == "today" else "workspace_tasks"
    return redirect(url_for(destination), code=303)


@app.get("/workspace/tasks")
@login_required
def workspace_tasks():
    return render_workspace_tasks()


@app.post("/workspace/tasks")
@login_required
def workspace_create_task():
    values = task_form_values()
    try:
        task_store.create_task(get_current_user_id(), current_user.username, timestamp=get_current_time(), **values)
    except task_store.TaskValidationError as error:
        return render_workspace_tasks(form_values=values, form_error=str(error)), 400
    flash("Task added.", "success")
    return redirect_after_task_change()


@app.route("/workspace/tasks/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def workspace_edit_task(task_id):
    owner_id, username = get_current_user_id(), current_user.username
    editing_task = task_store.get_task(owner_id, username, task_id, today=get_current_time().date())
    if request.method == "POST":
        values = task_form_values()
        try:
            task_store.update_task(owner_id, username, task_id, **values)
        except task_store.TaskValidationError as error:
            return render_workspace_tasks(
                editing_task=editing_task, form_values=values, form_error=str(error), return_to=request.form.get("return_to"),
            ), 400
        flash("Task updated.", "success")
        return redirect_after_task_change()
    return render_workspace_tasks(editing_task=editing_task, return_to=request.args.get("return_to"))


@app.post("/workspace/tasks/<int:task_id>/status")
@login_required
def workspace_set_task_status(task_id):
    completed = request.form.get("completed")
    if completed not in {"0", "1"}:
        return "Invalid task status.", 400
    task_store.set_task_completed(
        get_current_user_id(), current_user.username, task_id,
        completed=completed == "1", timestamp=get_current_time(),
    )
    flash("Task completed." if completed == "1" else "Task reopened.", "success")
    return redirect_after_task_change()


@app.post("/workspace/tasks/<int:task_id>/delete")
@login_required
def workspace_delete_task(task_id):
    task_store.delete_task(get_current_user_id(), current_user.username, task_id)
    flash("Task deleted.", "success")
    return redirect_after_task_change()


@app.errorhandler(task_store.TaskNotFound)
def handle_missing_task(error):
    if request.is_json or request.method == "DELETE":
        return jsonify({"error": "Task not found."}), 404
    return "Task not found.", 404


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
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Task details are required."}), 400
    task_type = data.get("type") or "daily"
    if not isinstance(task_type, str):
        return jsonify({"error": "Unsupported task type."}), 400
    try:
        task_store.create_task(
            get_current_user_id(), current_user.username,
            title=data.get("task"), priority=normalize_priority(data.get("priority")),
            task_type=task_type.strip().lower(), timestamp=get_current_time(),
        )
    except task_store.TaskValidationError as error:
        return jsonify({"error": str(error)}), 400

    today_entry = get_today_entry()
    return jsonify({
        "message": "Task added.",
        "dashboard_state": build_dashboard_state(today_entry) if today_entry else None,
    })


@app.route("/tasks", methods=["GET"])
@api_login_required
def get_tasks():
    tasks = task_store.list_tasks(get_current_user_id(), current_user.username, today=get_current_time().date())
    return jsonify([
        {
            "id": task["id"],
            "name": task["title"],
            "priority": task["priority"],
            "entry_date": task["entry_date"].isoformat() if task["entry_date"] else "",
            "type": task["task_type"],
            "completed": task["stored_completed"],
            "streak_count": task["stored_streak_count"],
            "last_completed_date": task["last_completed_date"],
        }
        for task in tasks
    ])


@app.route("/delete_task/<int:task_id>", methods=["DELETE"])
@api_login_required
def delete_task(task_id):
    task_store.delete_task(get_current_user_id(), current_user.username, task_id)
    today_entry = get_today_entry()
    return jsonify({
        "status": "deleted",
        "message": "Task deleted.",
        "dashboard_state": build_dashboard_state(today_entry) if today_entry else None,
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
        return jsonify({"redirect_url": url_for("daily_setup")}), 404

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
    with closing(get_db_connection()) as conn, conn:
        conn.execute(
            "UPDATE daily_entries SET is_cleared = 1 WHERE user = ? AND entry_date = ? AND is_cleared = 0",
            (current_user.username, get_today_string()),
        )

    return jsonify({
        "message": "Daily setup is ready to update.",
        "redirect_url": url_for("daily_setup", day_reset=1),
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
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or type(data.get("completed")) is not bool:
        return jsonify({"error": "A task completion status is required."}), 400
    task_type = data.get("type") or "daily"
    if not isinstance(task_type, str) or task_type.strip().lower() not in {"daily", "long_term"}:
        return jsonify({"error": "Unsupported task type."}), 400
    task_type = task_type.strip().lower()

    user_id, username = get_current_user_id(), current_user.username
    timestamp = get_current_time()
    today = timestamp.date()
    task_id = data.get("task_id")
    if task_id is None and task_type == "daily":
        # Older dashboard clients sent the name instead of the stable task ID.
        task_name = data.get("task_name")
        if not isinstance(task_name, str) or not task_name.strip():
            return jsonify({"error": "Task not found."}), 404
        task = next(
            (row for row in task_store.list_tasks(user_id, username, today=today, task_type="daily", entry_date=today)
             if row["title"] == task_name.strip()),
            None,
        )
    else:
        try:
            task_id = int(str(task_id))
        except ValueError:
            return jsonify({"error": "Task not found."}), 404
        task = task_store.get_task(user_id, username, task_id, today=today)

    if not task or task["task_type"] != task_type or (task_type == "daily" and task["entry_date"] != today):
        return jsonify({"error": "Task not found."}), 404
    task_store.set_task_completed(user_id, username, task["id"], completed=data["completed"], timestamp=timestamp)

    today_entry = get_today_entry()
    return jsonify({
        "message": "Task progress updated.",
        "dashboard_state": build_dashboard_state(today_entry) if today_entry else None,
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
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        return jsonify({"error": "Please add at least one task for today."}), 400

    tasks = normalize_task_list(data["tasks"])
    mood = data.get("mood")
    mood = mood.strip() if isinstance(mood, str) else ""
    exercised = parse_exercise_value(data.get("exercised"))

    try:
        sleep_hours = float(data.get("sleep_hours"))
    except (TypeError, ValueError):
        sleep_hours = None

    if not tasks:
        return jsonify({"error": "Please add at least one task for today."}), 400

    if sleep_hours is None or not 0 <= sleep_hours <= 24:
        return jsonify({"error": "Hours slept must be a number between 0 and 24."}), 400

    if mood not in {"Focused", "Neutral", "Stressed", "Low Energy"}:
        return jsonify({"error": "Please choose your mood for today."}), 400

    if exercised is None:
        return jsonify({"error": "Please choose whether you exercised today."}), 400

    plan = generate_start_day_plan(tasks, sleep_hours, mood, exercised)
    username = current_user.username
    now = get_current_time()
    entry_date = now.date().isoformat()
    try:
        with closing(get_db_connection()) as conn, conn:
            conn.execute(
                """
                INSERT INTO daily_entries (
                    user, entry_date, tasks_json, sleep_hours, study_hours_total,
                    mood, energy_level, exercised, plan, completed_tasks_json,
                    energy_percent, calories_override, energy_answers_json, is_cleared, created_at
                ) VALUES (?, ?, '[]', ?, 0, ?, 0, ?, ?, '[]', 0, NULL, '[]', 0, ?)
                ON CONFLICT(user, entry_date) DO UPDATE SET
                    sleep_hours = excluded.sleep_hours,
                    mood = excluded.mood,
                    energy_level = excluded.energy_level,
                    exercised = excluded.exercised,
                    plan = excluded.plan,
                    is_cleared = excluded.is_cleared,
                    created_at = excluded.created_at
                """,
                (username, entry_date, sleep_hours, mood, int(exercised), plan, now.isoformat(timespec="seconds")),
            )
            task_store.add_daily_setup_tasks(
                conn, get_current_user_id(), username, task_names=tasks, timestamp=now,
            )
    except task_store.TaskValidationError as error:
        return jsonify({"error": str(error)}), 400

    session["last_onboarding_date"] = entry_date
    return jsonify({"plan": plan, "redirect_url": url_for("dashboard", legacy=1)})


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
