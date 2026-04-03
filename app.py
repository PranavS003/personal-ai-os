import json
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pathlib import Path
from openai import OpenAI
from werkzeug.security import check_password_hash, generate_password_hash

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# ✅ ADD THIS PART HERE
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env")

# ✅ THEN use it here
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "personal-ai-os-dev-secret")

CHAT_SESSIONS = {}
MAX_CHAT_MESSAGES = 20
AI_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
DATABASE_PATH = os.environ.get("PERSONAL_AI_OS_DB", "database.db")
APP_TIMEZONE = os.environ.get("PERSONAL_AI_OS_TIMEZONE", "Asia/Kolkata")
SYSTEM_PROMPT = (
    "You are the helpful AI assistant inside Personal AI OS, a productivity dashboard. "
    "Give concise, practical, friendly answers that help the user plan, learn, and stay consistent. "
    "When the user asks for study help, tailor your suggestions using their current tasks, habits, and recent study history."
)
ENERGY_QUESTION_COUNT = 6
WORKOUT_CALORIE_RATES = {
    "Walking": 4,
    "Jogging": 7,
    "Running": 10,
    "Gym": 6,
}
TASK_PRIORITIES = {"High", "Medium", "Low"}
AI_ACTION_PROMPTS = {
    "energy": "Give 3 quick ways to boost energy right now.",
    "study": "Create a simple study plan for today.",
    "evening": "Plan a productive evening with study and relaxation.",
    "focus": "Suggest a focused work session plan.",
}
AI_ACTION_FALLBACKS = {
    "energy": "Try a quick reset: drink water, stand up, walk for 5 minutes, and start one small task right away.",
    "study": "Study in two 25-minute sessions with a 5-minute break between them, and start with the hardest topic first.",
    "evening": "Do one focused study block, take a short break, then finish with a light review and a calm wind-down.",
    "focus": "Work for 25 minutes on one priority, silence distractions, then take a 5-minute break before the next block.",
}


def get_ai_client():
    if OpenAI is None:
        raise RuntimeError("OpenAI SDK is not installed on the server.")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set on the server.")

    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )


def get_db_connection():
    return sqlite3.connect(DATABASE_PATH)


def get_current_time():
    try:
        return datetime.now(ZoneInfo(APP_TIMEZONE))
    except Exception:
        return datetime.now()


def get_today_string():
    return get_current_time().date().isoformat()


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


def get_current_user_id():
    try:
        return int(session.get("user_id"))
    except (TypeError, ValueError):
        return None


def get_current_user_record():
    return get_user_by_id(get_current_user_id())


def get_current_user():
    record = get_current_user_record()
    if not record:
        return None
    return record["username"]


def format_user_name(username):
    return username.capitalize()


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped_view


def api_login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not get_current_user():
            return jsonify({
                "error": "Please log in to continue.",
                "redirect_url": url_for("login"),
            }), 401
        return view_func(*args, **kwargs)

    return wrapped_view


def normalize_task_list(task_list):
    cleaned_tasks = []
    seen = set()

    for task in task_list:
        if not isinstance(task, str):
            continue
        cleaned = task.strip()
        if not cleaned:
            continue
        normalized = cleaned.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned_tasks.append(cleaned)

    return cleaned_tasks


def normalize_priority(value):
    cleaned = (value or "").strip().capitalize()
    if cleaned in TASK_PRIORITIES:
        return cleaned
    return "Medium"


def parse_exercise_value(value):
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"yes", "true", "1"}:
            return True
        if normalized in {"no", "false", "0"}:
            return False

    return None


def generate_start_day_plan(tasks, sleep_hours, mood, exercised):
    plan_parts = []

    if sleep_hours < 6:
        plan_parts.append("Take it easy today. Avoid heavy work.")

    if mood == "Stressed":
        plan_parts.append("Take breaks and avoid overload.")

    if not exercised:
        plan_parts.append("Try a short walk today.")

    if tasks:
        plan_parts.append(f"Begin with {tasks[0]} and move through the rest one step at a time.")

    if not plan_parts:
        plan_parts.append("You are set up for a balanced day. Start with your top priority and keep your momentum steady.")

    return " ".join(plan_parts)


def format_progress_value(value):
    if int(value) == value:
        return str(int(value))
    return f"{value:.1f}".rstrip("0").rstrip(".")


def parse_iso_date(value):
    if not value:
        return None

    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def coerce_json_list(value):
    if isinstance(value, list):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return parsed

    return []


def normalize_date_history(values):
    normalized = []
    seen = set()

    for raw_value in coerce_json_list(values):
        parsed = parse_iso_date(raw_value)
        if not parsed:
            continue
        iso_value = parsed.isoformat()
        if iso_value in seen:
            continue
        seen.add(iso_value)
        normalized.append(iso_value)

    normalized.sort()
    return normalized


def compute_streak_from_history(values):
    history = normalize_date_history(values)
    if not history:
        return 0

    history_set = set(history)
    current_day = parse_iso_date(get_today_string())
    streak = 0

    while current_day and current_day.isoformat() in history_set:
        streak += 1
        current_day -= timedelta(days=1)

    return streak


def get_bmi_category(bmi_value):
    if bmi_value < 18.5:
        return "Underweight"
    if bmi_value <= 24.9:
        return "Normal"
    return "Overweight"


def calculate_health_insight(height_cm, weight_kg):
    height_m = height_cm / 100
    bmi_value = weight_kg / (height_m ** 2)
    ideal_min = 18.5 * (height_m ** 2)
    ideal_max = 24.9 * (height_m ** 2)

    return {
        "height_cm": round(height_cm, 1),
        "weight_kg": round(weight_kg, 1),
        "bmi": round(bmi_value, 1),
        "category": get_bmi_category(bmi_value),
        "ideal_weight_min": round(ideal_min, 1),
        "ideal_weight_max": round(ideal_max, 1),
    }


def ensure_column(cursor, table_name, column_name, definition):
    existing_columns = {
        row[1]
        for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing_columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def ensure_daily_entries_schema(cursor):
    # Rebuild the daily table when needed so each user gets one entry per date.
    table_exists = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'daily_entries'"
    ).fetchone()

    desired_sql = """
        CREATE TABLE IF NOT EXISTS daily_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT NOT NULL,
            entry_date TEXT NOT NULL,
            tasks_json TEXT NOT NULL,
            sleep_hours REAL NOT NULL,
            study_hours_total REAL NOT NULL DEFAULT 0,
            mood TEXT NOT NULL,
            energy_level INTEGER NOT NULL DEFAULT 0,
            exercised INTEGER NOT NULL,
            plan TEXT NOT NULL,
            completed_tasks_json TEXT NOT NULL DEFAULT '[]',
            energy_percent INTEGER NOT NULL DEFAULT 0,
            calories_override INTEGER,
            energy_answers_json TEXT NOT NULL DEFAULT '[]',
            is_cleared INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(user, entry_date)
        )
    """

    if not table_exists:
        cursor.execute(desired_sql)
        return

    existing_columns = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(daily_entries)").fetchall()
    }
    index_rows = cursor.execute("PRAGMA index_list(daily_entries)").fetchall()
    has_user_date_unique_index = False
    for index_row in index_rows:
        if not index_row[2]:
            continue
        index_name = index_row[1]
        indexed_columns = [
            info_row[2]
            for info_row in cursor.execute(f"PRAGMA index_info({index_name})").fetchall()
        ]
        if indexed_columns == ["user", "entry_date"]:
            has_user_date_unique_index = True
            break

    if "user" in existing_columns and has_user_date_unique_index:
        ensure_column(cursor, "daily_entries", "study_hours_total", "REAL NOT NULL DEFAULT 0")
        ensure_column(cursor, "daily_entries", "completed_tasks_json", "TEXT NOT NULL DEFAULT '[]'")
        ensure_column(cursor, "daily_entries", "energy_percent", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(cursor, "daily_entries", "calories_override", "INTEGER")
        ensure_column(cursor, "daily_entries", "energy_answers_json", "TEXT NOT NULL DEFAULT '[]'")
        ensure_column(cursor, "daily_entries", "is_cleared", "INTEGER NOT NULL DEFAULT 0")
        return

    cursor.execute("ALTER TABLE daily_entries RENAME TO daily_entries_old")
    cursor.execute(desired_sql)

    old_columns = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(daily_entries_old)").fetchall()
    }

    user_expression = "user" if "user" in old_columns else "''"
    completed_expression = (
        "COALESCE(completed_tasks_json, '[]')"
        if "completed_tasks_json" in old_columns else
        "'[]'"
    )
    energy_percent_expression = (
        "COALESCE(energy_percent, 0)"
        if "energy_percent" in old_columns else
        "0"
    )
    energy_answers_expression = (
        "COALESCE(energy_answers_json, '[]')"
        if "energy_answers_json" in old_columns else
        "'[]'"
    )
    calories_override_expression = (
        "calories_override"
        if "calories_override" in old_columns else
        "NULL"
    )
    is_cleared_expression = (
        "COALESCE(is_cleared, 0)"
        if "is_cleared" in old_columns else
        "0"
    )
    energy_level_expression = (
        "COALESCE(energy_level, 0)"
        if "energy_level" in old_columns else
        "0"
    )
    study_hours_expression = (
        "COALESCE(study_hours_total, 0)"
        if "study_hours_total" in old_columns else
        "0"
    )

    cursor.execute(
        f"""
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
        )
        SELECT
            {user_expression},
            entry_date,
            tasks_json,
            sleep_hours,
            {study_hours_expression},
            mood,
            {energy_level_expression},
            exercised,
            plan,
            {completed_expression},
            {energy_percent_expression},
            {calories_override_expression},
            {energy_answers_expression},
            {is_cleared_expression},
            created_at
        FROM daily_entries_old
        """
    )
    cursor.execute("DROP TABLE daily_entries_old")


def get_today_entry(user=None):
    # Keep one onboarding entry per calendar day so refreshes skip setup after completion.
    current_user = user or get_current_user()
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
    current_user = user or get_current_user()
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
        "username": user or get_current_user(),
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


def get_latest_energy_log(user_id=None):
    current_user_id = user_id or get_current_user_id()
    if not current_user_id:
        return None

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT score, entry_date, answers_json
        FROM energy_logs
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

    return {
        "score": int(row[0] or 0),
        "entry_date": row[1],
        "answers": coerce_json_list(row[2]),
    }


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

    return {
        "height_cm": row[0],
        "weight_kg": row[1],
        "bmi": row[2],
        "category": row[3],
        "ideal_weight_min": row[4],
        "ideal_weight_max": row[5],
        "entry_date": row[6],
    }


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


def generate_daily_plan(data):
    sleep_hours = float(data.get("sleep_hours") or 0)
    energy = int(data.get("energy_percent") or 0)
    pending_tasks = data.get("pending_tasks") or []
    completed_tasks = data.get("completed_tasks") or []
    study_hours = float(data.get("study_hours") or 0)
    exercise_minutes = int(data.get("exercise_minutes") or 0)
    calories_burned = int(data.get("calories_burned") or 0)
    current_hour = int(data.get("current_hour") or get_current_time().hour)

    suggestions = []

    if sleep_hours < 5:
        suggestions.append("Keep today light: reading, planning, and low-intensity work first.")
    elif energy < 40:
        suggestions.append("Start with lighter tasks like review, reading, or planning.")
    elif energy <= 70:
        suggestions.append("Use 1 or 2 focused blocks for study, assignments, or admin tasks.")
    else:
        suggestions.append("Use your high energy for deep work on the hardest task first.")

    if pending_tasks:
        suggestions.append(f"Complete {pending_tasks[0]} next, then move to the remaining pending tasks.")
    elif completed_tasks:
        suggestions.append("You cleared your main tasks. Do a quick review and set up tomorrow's top priority.")
    else:
        suggestions.append("Add 1 or 2 clear tasks so the plan can become more specific.")

    if study_hours < 1:
        suggestions.append("Study for 1 hour in two short focused sessions.")
    elif study_hours < 3 and energy >= 40:
        suggestions.append("Add one more study block to keep momentum going.")

    if exercise_minutes < 10 and calories_burned < 120:
        suggestions.append("Exercise 10 to 15 minutes or take a brisk walk.")

    if current_hour >= 18:
        suggestions.append("Keep the evening calm: finish one meaningful task, then wind down.")
    elif current_hour < 12:
        suggestions.append("Protect the morning for your highest-focus work.")

    return suggestions[:4]


def build_dashboard_state(today_entry):
    sleep_goal = 8
    study_goal = 4
    exercise_goal = 30
    calories_goal = 400
    exercise_minutes = get_today_exercise_minutes()
    study_hours = get_today_study_hours()
    daily_tasks = get_today_task_records()
    if today_entry["tasks"] and not daily_tasks:
        sync_today_task_records(
            today_entry["tasks"],
            get_current_user(),
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
            "calories_burned": calories_burned,
            "completed_tasks": completed_tasks,
            "total_tasks": total_tasks,
            "pending_tasks": len(pending_tasks),
            "long_term_tasks": len(long_term_tasks),
        },
    }


def require_current_user():
    user = get_current_user()
    if not user:
        raise RuntimeError("User session is missing.")
    return user


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS study (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            hours INTEGER
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit TEXT,
            streak INTEGER DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT NOT NULL,
            entry_date TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            duration INTEGER NOT NULL,
            calories INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS energy_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            entry_date TEXT NOT NULL,
            answers_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, entry_date)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS health_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            entry_date TEXT NOT NULL,
            height_cm REAL NOT NULL,
            weight_kg REAL NOT NULL,
            bmi REAL NOT NULL,
            category TEXT NOT NULL,
            ideal_weight_min REAL NOT NULL,
            ideal_weight_max REAL NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, entry_date)
        )
        """
    )
    ensure_column(cur, "tasks", "user", "TEXT NOT NULL DEFAULT ''")
    ensure_column(cur, "tasks", "user_id", "INTEGER")
    ensure_column(cur, "tasks", "entry_date", "TEXT NOT NULL DEFAULT ''")
    ensure_column(cur, "tasks", "priority", "TEXT NOT NULL DEFAULT 'Medium'")
    ensure_column(cur, "tasks", "task_type", "TEXT NOT NULL DEFAULT 'daily'")
    ensure_column(cur, "tasks", "completed", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(cur, "tasks", "streak_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(cur, "tasks", "last_completed_date", "TEXT")
    ensure_column(cur, "tasks", "completion_history_json", "TEXT NOT NULL DEFAULT '[]'")
    ensure_column(cur, "tasks", "is_cleared", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(cur, "tasks", "created_at", "TEXT")
    ensure_column(cur, "study", "created_at", "TEXT")
    ensure_column(cur, "study", "user", "TEXT NOT NULL DEFAULT ''")
    ensure_column(cur, "habits", "user", "TEXT NOT NULL DEFAULT ''")
    ensure_column(cur, "workouts", "is_cleared", "INTEGER NOT NULL DEFAULT 0")
    ensure_daily_entries_schema(cur)
    cur.execute(
        """
        UPDATE tasks
        SET user_id = (
            SELECT users.id
            FROM users
            WHERE lower(users.username) = lower(tasks.user)
            LIMIT 1
        )
        WHERE (user_id IS NULL OR user_id = 0) AND user <> ''
        """
    )

    conn.commit()
    conn.close()


init_db()


def get_chat_session_id():
    chat_session_id = session.get("chat_session_id")
    if not chat_session_id:
        chat_session_id = str(uuid.uuid4())
        session["chat_session_id"] = chat_session_id
    return chat_session_id



def get_chat_history():
    user = get_current_user() or "guest"
    chat_session_id = get_chat_session_id()
    history_key = f"{user}:{chat_session_id}"
    return CHAT_SESSIONS.setdefault(history_key, [])



def trim_chat_history(history):
    if len(history) > MAX_CHAT_MESSAGES:
        del history[:-MAX_CHAT_MESSAGES]


def get_dashboard_context():
    current_user = get_current_user()
    today_entry = get_today_entry(current_user)
    workouts = get_today_workouts(current_user)
    long_term_tasks = get_long_term_task_records(current_user)
    health_data = get_latest_health_data()

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
    study_goal_text = "Target 4 hours today; progress not started."
    schedule_text = "No schedule captured yet."

    if today_entry:
        study_goal_text = (
            f"Target 4 hours today; current progress {format_progress_value(today_entry['study_hours_total'])} hour(s)."
        )
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
        f"- Backlog Tasks: {backlog_text}\n"
        f"- Long-Term Goals: {long_term_text}\n"
        f"- Health Insight: {health_text}"
    )


def insert_study_entry(subject, hours, user=None):
    current_user = user or get_current_user()
    if not current_user:
        raise RuntimeError("User session is missing.")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO study (subject, hours, created_at, user) VALUES (?, ?, ?, ?)",
        (subject, hours, get_current_time().isoformat(timespec="seconds"), current_user),
    )
    conn.commit()
    conn.close()


def set_study_hours_total(hours, user=None):
    current_user = user or get_current_user()
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
    current_user = user or get_current_user()
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



def extract_response_text(payload):
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    text_parts = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text = content.get("text", "").strip()
                if text:
                    text_parts.append(text)

    if text_parts:
        return "\n".join(text_parts)

    return "I could not generate a reply just now. Please try again."



def get_openai_reply(history, user_message, dashboard_context):
    messages = [
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
    ]

    for item in history:
        role = (item.get("role") or "").strip().lower()
        content = (item.get("content") or "").strip()
        if role in {"user", "assistant", "system"} and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})

    try:
        client = get_ai_client()
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
        )
    except Exception as exc:  # pragma: no cover - depends on live API/runtime
        error_text = str(exc).lower()
        if "insufficient_quota" in error_text or "quota" in error_text:
            return "AI is temporarily unavailable. Please check API usage."
        raise RuntimeError("AI is temporarily unavailable. Please try again.") from exc

    response_text = (
        response.choices[0].message.content.strip()
        if response.choices and response.choices[0].message.content
        else ""
    )

    return response_text or "I could not generate a reply just now. Please try again."


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = get_user_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("home"))

        return render_template("login.html", error="Invalid credentials")

    if get_current_user():
        return redirect(url_for("home"))

    return render_template("login.html", error=None)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        try:
            user_id = create_user_account(username, email, password)
        except ValueError as exc:
            return render_template(
                "register.html",
                error=str(exc),
                form_data={"username": username, "email": email},
            )

        session.clear()
        session["user_id"] = user_id
        return redirect(url_for("home"))

    if get_current_user():
        return redirect(url_for("home"))

    return render_template("register.html", error=None, form_data={"username": "", "email": ""})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def home():
    if get_today_entry():
        return redirect(url_for("dashboard"))

    return render_template(
        "onboarding.html",
        current_user_display=format_user_name(get_current_user()),
        day_notice="New day started. Ready to plan?" if request.args.get("day_reset") == "1" else None,
    )


@app.route("/dashboard")
@login_required
def dashboard():
    today_entry = get_today_entry()
    if not today_entry:
        return redirect(url_for("home"))
    dashboard_state = build_dashboard_state(today_entry)

    return render_template(
        "index.html",
        chat_history=get_chat_history(),
        today_entry=today_entry,
        dashboard_state=dashboard_state,
        current_user_display=format_user_name(get_current_user()),
    )


@app.route("/add_task", methods=["POST"])
@api_login_required
def add_task():
    current_user = get_current_user()
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
    current_user = get_current_user()
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
    current_user = get_current_user()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_cleared = 1 WHERE id = ? AND user = ?", (task_id, current_user))
    conn.commit()
    conn.close()

    return jsonify({"status": "deleted"})


@app.route("/add_study", methods=["POST"])
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

    try:
        set_study_hours_total(min(24, get_today_study_hours(current_user) + hours), current_user)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"message": "Study added"})


@app.route("/get_study", methods=["GET"])
@api_login_required
def get_study():
    current_user = get_current_user()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM study WHERE user = ? ORDER BY id DESC", (current_user,))
    data = cur.fetchall()
    conn.close()

    return jsonify(data)


@app.route("/add_habit", methods=["POST"])
@api_login_required
def add_habit():
    current_user = get_current_user()
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
    current_user = get_current_user()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM habits WHERE user = ? ORDER BY id DESC", (current_user,))
    data = cur.fetchall()
    conn.close()

    return jsonify(data)


@app.route("/update_streak/<int:habit_id>", methods=["POST"])
@api_login_required
def update_streak(habit_id):
    current_user = get_current_user()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE habits SET streak = streak + 1 WHERE id = ? AND user = ?", (habit_id, current_user))
    conn.commit()
    conn.close()

    return jsonify({"message": "Streak updated"})


@app.route("/get_stats", methods=["GET"])
@api_login_required
def get_stats():
    current_user = get_current_user()
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
        update_study_hours_total(action, value, get_current_user())
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
    current_user = get_current_user()
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
    current_user = get_current_user()
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
    current_user = get_current_user()
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
    current_user = get_current_user()
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

    try:
        bot_reply = get_openai_reply(history, user_message, dashboard_context)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": bot_reply})
    trim_chat_history(history)

    return jsonify({
        "response": bot_reply,
        "reply": bot_reply,
        "messages": history
    })


@app.route("/ai-action", methods=["POST"])
def ai_action():
    try:
        data = request.get_json()
        user_message = data.get("message", "")
        dashboard_context = get_dashboard_context()

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
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

    except Exception as e:  # pragma: no cover - depends on live API/runtime
        print("FULL ERROR:", str(e))
        return jsonify({"reply": "AI is temporarily unavailable."})


if __name__ == "__main__":
    app.run(debug=True)
