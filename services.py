import json
import os
import sqlite3
import uuid
from datetime import datetime
from functools import wraps
from urllib import error, request as urlrequest
from zoneinfo import ZoneInfo

from flask import jsonify, redirect, session, url_for

CHAT_SESSIONS = {}
MAX_CHAT_MESSAGES = 20
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
DATABASE_PATH = os.environ.get("PERSONAL_AI_OS_DB", "database.db")
APP_TIMEZONE = os.environ.get("PERSONAL_AI_OS_TIMEZONE", "Asia/Kolkata")
SYSTEM_PROMPT = (
    "You are the helpful AI assistant inside Personal AI OS, a productivity dashboard. "
    "Give concise, practical, friendly answers that help the user plan, learn, and stay consistent. "
    "When the user asks for study help, tailor your suggestions using their current tasks, habits, and recent study history."
)
ENERGY_QUESTION_COUNT = 10
VALID_USERS = {
    "pranav": "123",
    "alen": "123",
}
WORKOUT_CALORIE_RATES = {
    "Walking": 4,
    "Jogging": 7,
    "Running": 10,
    "Gym": 6,
}


def get_db_connection():
    return sqlite3.connect(DATABASE_PATH)


def get_current_time():
    try:
        return datetime.now(ZoneInfo(APP_TIMEZONE))
    except Exception:
        return datetime.now()


def get_today_string():
    return get_current_time().date().isoformat()


def get_current_user():
    user = session.get("user")
    if user in VALID_USERS:
        return user
    return None


def format_user_name(username):
    return username.capitalize()


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("auth.login"))
        return view_func(*args, **kwargs)

    return wrapped_view


def api_login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not get_current_user():
            return jsonify({
                "error": "Please log in to continue.",
                "redirect_url": url_for("auth.login"),
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


def generate_daily_plan(tasks, sleep_hours, mood, exercised):
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
            energy_answers_json TEXT NOT NULL DEFAULT '[]',
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
        ensure_column(cursor, "daily_entries", "energy_answers_json", "TEXT NOT NULL DEFAULT '[]'")
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
            energy_answers_json,
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
            {energy_answers_expression},
            created_at
        FROM daily_entries_old
        """
    )
    cursor.execute("DROP TABLE daily_entries_old")


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

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

    ensure_column(cur, "tasks", "user", "TEXT NOT NULL DEFAULT ''")
    ensure_column(cur, "study", "created_at", "TEXT")
    ensure_column(cur, "study", "user", "TEXT NOT NULL DEFAULT ''")
    ensure_column(cur, "habits", "user", "TEXT NOT NULL DEFAULT ''")
    ensure_daily_entries_schema(cur)

    conn.commit()
    conn.close()


def get_today_entry(user=None):
    current_user = user or get_current_user()
    if not current_user:
        return None

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
            energy_answers_json
        FROM daily_entries
        WHERE user = ? AND entry_date = ?
        """,
        (current_user, get_today_string()),
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
        energy_answers = json.loads(row[10])
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
        WHERE user = ? AND entry_date = ?
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
    workouts = get_today_workouts(user)
    return sum(int(item["calories"]) for item in workouts)


def get_today_exercise_minutes(user=None):
    workouts = get_today_workouts(user)
    return sum(int(item["duration"]) for item in workouts)


def build_ai_suggestions(today_entry, study_hours, exercise_minutes, calories_burned):
    suggestions = []

    if today_entry["sleep_hours"] < 6:
        suggestions.append("You need more rest. Avoid heavy work.")

    if today_entry["energy_checked"] and today_entry["energy_percent"] < 40:
        suggestions.append("Start with light tasks.")

    if exercise_minutes < 10:
        suggestions.append("Do 10-15 min walking.")

    if study_hours < 1:
        suggestions.append("Try 1 focused session today.")

    if calories_burned < 200:
        suggestions.append("You need more activity today.")

    if calories_burned > 400:
        suggestions.append("Great job staying active!")

    if not today_entry["energy_checked"]:
        suggestions.append("Check your energy to see how hard you should push today.")

    if not suggestions:
        suggestions.append("You are in a solid rhythm today. Protect your focus and finish your most important task first.")

    return suggestions


def build_dashboard_state(today_entry):
    sleep_goal = 8
    study_goal = 4
    exercise_goal = 30
    calories_goal = 400

    exercise_minutes = get_today_exercise_minutes()
    study_hours = get_today_study_hours()
    workouts = get_today_workouts()
    calories_burned = get_today_calories()
    sleep_ratio = min(today_entry["sleep_hours"] / sleep_goal, 1.0)
    energy_percent = max(0, min(int(today_entry["energy_percent"]), 100))
    study_ratio = min(study_hours / study_goal, 1.0)
    exercise_ratio = min(exercise_minutes / exercise_goal, 1.0)
    calories_ratio = min(calories_burned / calories_goal, 1.0)

    completed_lookup = set(today_entry["completed_tasks"])
    total_tasks = len(today_entry["tasks"])
    completed_tasks = sum(1 for task in today_entry["tasks"] if task in completed_lookup)

    return {
        "entry_date": today_entry["entry_date"],
        "suggestions": build_ai_suggestions(today_entry, study_hours, exercise_minutes, calories_burned),
        "metrics": [
            {
                "key": "exercise",
                "emoji": "\U0001F3C3",
                "label": "Exercise Ring",
                "value": f"{exercise_minutes} / {exercise_goal} min",
                "percent": round(exercise_ratio * 100),
                "theme": "exercise",
            },
            {
                "key": "calories",
                "emoji": "\U0001F525",
                "label": "Calories Ring",
                "value": f"{calories_burned} / {calories_goal} kcal",
                "percent": round(calories_ratio * 100),
                "theme": "calories",
            },
            {
                "key": "study",
                "emoji": "\U0001F4DA",
                "label": "Study Ring",
                "value": f"{format_progress_value(study_hours)} / {study_goal} hrs",
                "percent": round(study_ratio * 100),
                "theme": "study",
                "current_hours": study_hours,
            },
        ],
        "bars": {
            "sleep": {
                "emoji": "\U0001F634",
                "label": "Sleep",
                "value": f"{format_progress_value(today_entry['sleep_hours'])} / {sleep_goal} hrs",
                "percent": round(sleep_ratio * 100),
            },
            "energy": {
                "emoji": "\u26A1",
                "label": "Energy",
                "value": f"{energy_percent}%",
                "percent": energy_percent,
                "checked": today_entry["energy_checked"],
            },
        },
        "energy_check": {
            "checked": today_entry["energy_checked"],
            "percent": energy_percent,
        },
        "tasks": [
            {
                "name": task,
                "completed": task in completed_lookup,
            }
            for task in today_entry["tasks"]
        ],
        "workouts": workouts,
        "workout_summary": {
            "total_calories": calories_burned,
            "goal_calories": calories_goal,
            "total_minutes": exercise_minutes,
            "goal_minutes": exercise_goal,
        },
        "summary": {
            "sleep_hours": format_progress_value(today_entry["sleep_hours"]),
            "energy_percent": energy_percent,
            "exercise_minutes": exercise_minutes,
            "study_hours": format_progress_value(study_hours),
            "calories_burned": calories_burned,
            "completed_tasks": completed_tasks,
            "total_tasks": total_tasks,
        },
    }


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
    if not current_user:
        return "No dashboard context is available because no user is logged in."

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM tasks WHERE user = ? ORDER BY id DESC LIMIT 8", (current_user,))
    tasks = [row[0] for row in cur.fetchall()]
    cur.execute("SELECT habit, streak FROM habits WHERE user = ? ORDER BY id DESC LIMIT 8", (current_user,))
    habits = [{"name": row[0], "streak": row[1]} for row in cur.fetchall()]
    conn.close()

    today_entry = get_today_entry(current_user)
    task_text = ", ".join(tasks) if tasks else "No tasks added yet."
    habit_text = (
        ", ".join(f"{item['name']} (streak {item['streak']})" for item in habits)
        if habits else
        "No habits added yet."
    )
    study_text = "No study hours tracked yet."
    if today_entry:
        study_text = f"{format_progress_value(today_entry['study_hours_total'])} hour(s) tracked today."
    workout_entries = get_today_workouts(current_user)
    workout_text = (
        ", ".join(
            f"{item['activity_type']} for {item['duration']} min ({item['calories']} kcal)"
            for item in workout_entries[:5]
        )
        if workout_entries else
        "No workout activity tracked yet."
    )
    daily_setup_text = "No daily setup completed yet."
    if today_entry:
        daily_tasks = ", ".join(today_entry["tasks"]) if today_entry["tasks"] else "No daily tasks listed."
        exercise_text = "Yes" if today_entry["exercised"] else "No"
        energy_text = f"{today_entry['energy_percent']}%" if today_entry["energy_checked"] else "Not checked yet"
        daily_setup_text = (
            f"Tasks: {daily_tasks}; Sleep: {today_entry['sleep_hours']} hour(s); "
            f"Mood: {today_entry['mood']}; Energy: {energy_text}; "
            f"Exercise: {exercise_text}; Plan: {today_entry['plan']}"
        )

    return (
        "Current dashboard context:\n"
        f"- Tasks: {task_text}\n"
        f"- Habits: {habit_text}\n"
        f"- Recent study logs: {study_text}\n"
        f"- Today's workouts: {workout_text}\n"
        f"- Today's setup: {daily_setup_text}\n"
        "Use this context when giving study suggestions, revision plans, prioritization advice, or daily routines."
    )


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

    # Study tracking behaves like a single total for the current user and current date.
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

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE daily_entries
        SET study_hours_total = ?
        WHERE user = ? AND entry_date = ?
        """,
        (updated_hours, current_user, today_entry["entry_date"]),
    )
    conn.commit()
    conn.close()

    return updated_hours


def fetch_user_tasks(user=None):
    current_user = user or get_current_user()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM tasks WHERE user = ? ORDER BY id DESC", (current_user,))
    rows = cur.fetchall()
    conn.close()
    return [{"id": row[0], "name": row[1]} for row in rows]


def fetch_user_habits(user=None):
    current_user = user or get_current_user()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM habits WHERE user = ? ORDER BY id DESC", (current_user,))
    rows = cur.fetchall()
    conn.close()
    return rows


def fetch_dashboard_stats(user=None):
    current_user = user or get_current_user()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tasks WHERE user = ?", (current_user,))
    total_tasks = cur.fetchone()[0]
    cur.execute("SELECT SUM(hours) FROM study WHERE user = ?", (current_user,))
    total_study_hours = cur.fetchone()[0] or 0
    cur.execute("SELECT COUNT(*) FROM habits WHERE user = ?", (current_user,))
    total_habits = cur.fetchone()[0]
    conn.close()

    return {
        "tasks": total_tasks,
        "study_hours": total_study_hours,
        "habits": total_habits,
    }


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
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set on the server.")

    conversation = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": dashboard_context},
    ]
    conversation.extend(history)
    conversation.append({"role": "user", "content": user_message})

    payload = {
        "model": OPENAI_MODEL,
        "input": conversation,
        "max_output_tokens": 300,
    }

    req = urlrequest.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urlrequest.urlopen(req, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        try:
            error_json = json.loads(error_body)
            message = error_json.get("error", {}).get("message", "OpenAI request failed.")
        except json.JSONDecodeError:
            message = error_body or "OpenAI request failed."
        raise RuntimeError(message) from exc
    except error.URLError as exc:
        raise RuntimeError("Could not reach the OpenAI API. Check your internet connection.") from exc

    return extract_response_text(result)

