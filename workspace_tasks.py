import json
from contextlib import closing, contextmanager
from datetime import date, datetime
from sqlite3 import Row

from config import TASK_PRIORITIES
from database.db import get_db_connection
from utils.calculations import compute_streak_from_history
from utils.helpers import (
    coerce_json_list,
    normalize_date_history,
    normalize_priority,
    normalize_task_list,
    parse_iso_date,
)


class TaskValidationError(ValueError):
    pass


class TaskNotFound(LookupError):
    pass


_OWNER = "((user_id = ? AND user_id <> 0) OR (COALESCE(user_id, 0) = 0 AND user = ?))"
_TASK_COLUMNS = """
    id, name, priority, due_date, completed, completed_at, task_type, entry_date,
    streak_count, last_completed_date, completion_history_json
"""


@contextmanager
def _write_transaction():
    with closing(get_db_connection()) as conn, conn:
        conn.row_factory = Row
        conn.execute("BEGIN IMMEDIATE")
        yield conn


def _validate_fields(title, priority, due_date, *, existing_title=None):
    if not isinstance(title, str) or not title.strip():
        raise TaskValidationError("Enter a task title.")
    title = title.strip()
    if len(title) > 200 and title != existing_title:
        raise TaskValidationError("A task title can be at most 200 characters.")

    priority = priority.strip().capitalize() if isinstance(priority, str) else ""
    if priority not in TASK_PRIORITIES:
        raise TaskValidationError("Choose a valid priority.")

    if due_date is None or due_date == "":
        return title, priority, None
    if isinstance(due_date, date) and not isinstance(due_date, datetime):
        return title, priority, due_date.isoformat()
    deadline = parse_iso_date(due_date) if isinstance(due_date, str) else None
    if deadline is None or deadline.isoformat() != due_date:
        raise TaskValidationError("Enter a valid deadline in YYYY-MM-DD format.")
    return title, priority, due_date


def _find_task(conn, user_id, username, task_id):
    if not isinstance(task_id, int) or not 0 < task_id < 2**63:
        raise TaskNotFound("Task not found.")
    row = conn.execute(
        f"SELECT {_TASK_COLUMNS} FROM tasks WHERE id = ? AND {_OWNER} AND is_cleared = 0",
        (task_id, user_id, username),
    ).fetchone()
    if row is None:
        raise TaskNotFound("Task not found.")
    return row


def _task_data(row, today):
    stored_completed = bool(row["completed"])
    completed = stored_completed
    stored_streak_count = row["streak_count"] or 0
    streak_count = stored_streak_count
    if row["task_type"] == "long_term":
        history = normalize_date_history(row["completion_history_json"])
        completed = today.isoformat() in history
        streak_count = compute_streak_from_history(history, today=today)

    return {
        "id": row["id"],
        "title": row["name"],
        "priority": normalize_priority(row["priority"]),
        "due_date": parse_iso_date(row["due_date"]),
        "completed": completed,
        "task_type": row["task_type"],
        "entry_date": parse_iso_date(row["entry_date"]),
        "streak_count": streak_count,
        "stored_streak_count": stored_streak_count,
        "last_completed_date": row["last_completed_date"],
        "stored_completed": stored_completed,
    }


def list_tasks(user_id, username, *, today: date, task_type=None, entry_date: date | None = None, limit=None):
    query = f"SELECT {_TASK_COLUMNS} FROM tasks WHERE {_OWNER} AND is_cleared = 0"
    params = (user_id, username)
    if task_type is not None:
        query += " AND task_type = ?"
        params += (task_type,)
    if entry_date is not None:
        query += " AND entry_date = ?"
        params += (entry_date.isoformat(),)
    query += " ORDER BY id DESC"
    if limit is not None:
        query += " LIMIT ?"
        params += (limit,)

    with closing(get_db_connection()) as conn:
        conn.row_factory = Row
        rows = conn.execute(query, params).fetchall()
    return [_task_data(row, today) for row in rows]


def get_task(user_id, username, task_id, *, today: date):
    with closing(get_db_connection()) as conn:
        conn.row_factory = Row
        return _task_data(_find_task(conn, user_id, username, task_id), today)


def _assert_unique_name(conn, user_id, username, task_type, entry_date, title, task_id=None):
    query = f"SELECT id, name FROM tasks WHERE {_OWNER} AND task_type = ? AND is_cleared = 0"
    params = (user_id, username, task_type)
    if task_type == "daily":
        query += " AND entry_date = ?"
        params += (entry_date,)

    for existing_id, name in conn.execute(query, params):
        if existing_id != task_id and isinstance(name, str) and name.strip().casefold() == title.casefold():
            raise TaskValidationError("A task with that title already exists.")


def _insert_task(
    conn, user_id, username, *, title, priority, entry_date, created_at,
    task_type="daily", due_date=None, completed=False,
):
    return conn.execute(
        """
        INSERT INTO tasks (user_id, user, name, priority, entry_date, created_at, task_type, due_date, completed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, username, title, priority, entry_date, created_at, task_type, due_date, int(completed)),
    ).lastrowid


def _project_daily_tasks(conn, user_id, username, entry_date):
    rows = conn.execute(
        f"""
        SELECT name, completed FROM tasks
        WHERE {_OWNER} AND task_type = 'daily' AND entry_date = ? AND is_cleared = 0
        ORDER BY id
        """,
        (user_id, username, entry_date),
    ).fetchall()
    titles = normalize_task_list([name for name, _ in rows])
    completed_names = {name.strip() for name, completed in rows if isinstance(name, str) and completed}
    completed_titles = [title for title in titles if title in completed_names]
    conn.execute(
        """
        UPDATE daily_entries SET tasks_json = ?, completed_tasks_json = ?
        WHERE user = ? AND entry_date = ? AND is_cleared = 0
        """,
        (json.dumps(titles), json.dumps(completed_titles), username, entry_date),
    )


def create_task(user_id, username, *, title, priority, due_date=None, timestamp: datetime, task_type="daily"):
    title, priority, deadline = _validate_fields(title, priority, due_date)
    if task_type not in ("daily", "long_term"):
        raise TaskValidationError("Choose a valid task type.")

    entry_date = timestamp.date().isoformat()
    with _write_transaction() as conn:
        _assert_unique_name(conn, user_id, username, task_type, entry_date, title)
        task_id = _insert_task(
            conn, user_id, username, title=title, priority=priority, entry_date=entry_date,
            created_at=timestamp.isoformat(timespec="seconds"), task_type=task_type, due_date=deadline,
        )
        if task_type == "daily":
            _project_daily_tasks(conn, user_id, username, entry_date)
    return task_id


def update_task(user_id, username, task_id, *, title, priority, due_date=None):
    with _write_transaction() as conn:
        task = _find_task(conn, user_id, username, task_id)
        title, priority, deadline = _validate_fields(title, priority, due_date, existing_title=task["name"])
        if not isinstance(task["name"], str) or task["name"].strip().casefold() != title.casefold():
            _assert_unique_name(conn, user_id, username, task["task_type"], task["entry_date"], title, task_id)
        conn.execute(
            "UPDATE tasks SET name = ?, priority = ?, due_date = ? WHERE id = ?",
            (title, priority, deadline, task_id),
        )
        if task["task_type"] == "daily":
            _project_daily_tasks(conn, user_id, username, task["entry_date"])


def set_task_completed(user_id, username, task_id, *, completed: bool, timestamp: datetime):
    if not isinstance(completed, bool):
        raise TaskValidationError("Choose a valid completion status.")

    with _write_transaction() as conn:
        task = _find_task(conn, user_id, username, task_id)
        if task["task_type"] == "long_term":
            current_day = timestamp.date().isoformat()
            history = set(normalize_date_history(task["completion_history_json"]))
            completed_at = task["completed_at"]
            if completed and current_day not in history:
                history.add(current_day)
                completed_at = timestamp.isoformat(timespec="seconds")
            elif not completed and current_day in history:
                history.remove(current_day)
                completed_at = None
            dates = sorted(history)
            conn.execute(
                """
                UPDATE tasks
                SET completed = ?, completed_at = ?, streak_count = ?, last_completed_date = ?, completion_history_json = ?
                WHERE id = ?
                """,
                (int(completed), completed_at, compute_streak_from_history(dates, today=timestamp.date()),
                 dates[-1] if dates else None, json.dumps(dates), task_id),
            )
        elif completed != bool(task["completed"]):
            conn.execute(
                "UPDATE tasks SET completed = ?, completed_at = ? WHERE id = ?",
                (int(completed), timestamp.isoformat(timespec="seconds") if completed else None, task_id),
            )
            _project_daily_tasks(conn, user_id, username, task["entry_date"])


def delete_task(user_id, username, task_id):
    with _write_transaction() as conn:
        task = _find_task(conn, user_id, username, task_id)
        conn.execute("UPDATE tasks SET is_cleared = 1 WHERE id = ?", (task_id,))
        if task["task_type"] == "daily":
            _project_daily_tasks(conn, user_id, username, task["entry_date"])


def add_daily_setup_tasks(conn, user_id, username, *, task_names, timestamp: datetime):
    """Merge setup additions into canonical tasks within the caller's day write."""
    entry_date = timestamp.date().isoformat()
    existing = _daily_task_names(conn, user_id, username, entry_date, include_cleared=False)
    for name in normalize_task_list(task_names):
        if name.casefold() in existing:
            continue
        title, priority, _ = _validate_fields(name, "Medium", None)
        _insert_task(
            conn, user_id, username, title=title, priority=priority, entry_date=entry_date,
            created_at=timestamp.isoformat(timespec="seconds"),
        )
    _project_daily_tasks(conn, user_id, username, entry_date)


def _daily_task_names(conn, user_id, username, entry_date, *, include_cleared):
    query = f"SELECT name FROM tasks WHERE {_OWNER} AND task_type = 'daily' AND entry_date = ?"
    if not include_cleared:
        query += " AND is_cleared = 0"
    return {
        name.strip().casefold()
        for (name,) in conn.execute(query, (user_id, username, entry_date))
        if isinstance(name, str)
    }


def import_legacy_daily_tasks(conn):
    """Import JSON-only tasks while leaving existing rows and day snapshots intact."""
    entries = conn.execute(
        """
        SELECT users.id, daily_entries.user, entry_date, tasks_json, completed_tasks_json
        FROM daily_entries JOIN users ON users.username = daily_entries.user
        WHERE daily_entries.is_cleared = 0
        """
    )
    for user_id, username, entry_date, titles_json, completed_json in entries:
        titles = normalize_task_list(coerce_json_list(titles_json))
        if not titles:
            continue
        completed_titles = {title.casefold() for title in normalize_task_list(coerce_json_list(completed_json))}
        existing = _daily_task_names(conn, user_id, username, entry_date, include_cleared=True)
        for title in titles:
            if title.casefold() in existing:
                continue
            _insert_task(
                conn, user_id, username, title=title, priority="Medium", entry_date=entry_date,
                created_at=None, completed=title.casefold() in completed_titles,
            )
