import json
import logging
import sys
from datetime import date, datetime
from functools import wraps
from zoneinfo import ZoneInfo

from flask import jsonify, redirect, render_template, url_for
from flask_login import current_user
from jinja2 import TemplateNotFound

from config import (
    APP_TIMEZONE,
    DATABASE_FILE,
    STATIC_CSS_DIR,
    STATIC_DIR,
    STATIC_JS_DIR,
    TASK_PRIORITIES,
    TEMPLATES_DIR,
)


APP_LOGGER = None


def set_app_logger(logger):
    global APP_LOGGER
    APP_LOGGER = logger


def configure_logging(flask_app):
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    gunicorn_logger = logging.getLogger("gunicorn.error")
    root_logger = logging.getLogger()

    if gunicorn_logger.handlers:
        flask_app.logger.handlers = gunicorn_logger.handlers
        flask_app.logger.setLevel(gunicorn_logger.level or logging.INFO)
        root_logger.handlers = gunicorn_logger.handlers
        root_logger.setLevel(gunicorn_logger.level or logging.INFO)
    else:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)

        if not root_logger.handlers:
            root_logger.addHandler(stream_handler)
        else:
            for handler in root_logger.handlers:
                handler.setFormatter(formatter)

        root_logger.setLevel(logging.INFO)
        flask_app.logger.handlers = root_logger.handlers
        flask_app.logger.setLevel(root_logger.level)

    flask_app.logger.propagate = False
    logging.captureWarnings(True)


def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.getLogger("personal_ai_os").critical(
        "Uncaught exception during startup/runtime.",
        exc_info=(exc_type, exc_value, exc_traceback),
    )


def ensure_directory(path, label):
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:  # pragma: no cover - depends on filesystem/runtime
        logger = APP_LOGGER or logging.getLogger("personal_ai_os")
        logger.exception("Unable to prepare %s at %s", label, path)


def prepare_runtime_paths(logger):
    ensure_directory(TEMPLATES_DIR, "templates directory")
    ensure_directory(STATIC_DIR, "static directory")
    ensure_directory(STATIC_CSS_DIR, "static css directory")
    ensure_directory(STATIC_JS_DIR, "static js directory")
    ensure_directory(DATABASE_FILE.parent, "database directory")

    for template_name in ("index.html", "login.html", "onboarding.html", "register.html"):
        template_path = TEMPLATES_DIR / template_name
        if not template_path.exists():
            logger.warning("Expected template is missing: %s", template_path)


def safe_render_template(template_name, **context):
    template_path = TEMPLATES_DIR / template_name
    logger = APP_LOGGER or logging.getLogger("personal_ai_os")
    if not template_path.exists():
        logger.error("Template file missing: %s", template_path)
        return f"Template '{template_name}' is missing on the server.", 500

    try:
        return render_template(template_name, **context)
    except TemplateNotFound:  # pragma: no cover - depends on deployment assets
        logger.exception("Template resolution failed for %s", template_name)
        return f"Template '{template_name}' could not be loaded.", 500


def get_current_time():
    try:
        return datetime.now(ZoneInfo(APP_TIMEZONE))
    except Exception:
        return datetime.now()


def get_today_string():
    return get_current_time().date().isoformat()


def format_user_name(username):
    return username.capitalize()


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped_view


def api_login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated:
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


def normalize_career_text(value, field_name):
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required.")
    return cleaned


def normalize_study_subjects(values):
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    elif not isinstance(values, list):
        values = []

    cleaned_subjects = []
    seen = set()
    for item in values:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned:
            continue
        normalized = cleaned.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned_subjects.append(cleaned)

    return cleaned_subjects
