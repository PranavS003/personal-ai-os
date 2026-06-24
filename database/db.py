import sqlite3

from config import DATABASE_FILE, DATABASE_PATH
from utils.helpers import ensure_directory


def get_db_connection():
    ensure_directory(DATABASE_FILE.parent, "database directory")
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


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


def init_db(logger):
    conn = get_db_connection()
    try:
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
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS career_pipeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                company_name TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                next_action TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS career_skill_focus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                UNIQUE(user, skill_name)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS career_study_tracker (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                study_hours REAL NOT NULL DEFAULT 0,
                target_hours REAL NOT NULL DEFAULT 4,
                subjects_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL,
                UNIQUE(user, entry_date)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS career_subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                subject_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user, subject_name)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at REAL NOT NULL,
                created_at TEXT NOT NULL
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
        ensure_column(cur, "career_study_tracker", "target_hours", "REAL NOT NULL DEFAULT 4")
        ensure_column(cur, "career_study_tracker", "subjects_json", "TEXT NOT NULL DEFAULT '[]'")
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
        logger.info("SQLite database is ready at %s", DATABASE_PATH)
    except Exception:
        logger.exception("Database initialization failed for %s", DATABASE_PATH)
        raise
    finally:
        conn.close()
