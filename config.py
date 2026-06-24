import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STATIC_CSS_DIR = STATIC_DIR / "css"
STATIC_JS_DIR = STATIC_DIR / "js"
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH)


def resolve_runtime_path(value, default_name):
    raw_path = Path(value) if value else (BASE_DIR / default_name)
    if not raw_path.is_absolute():
        raw_path = BASE_DIR / raw_path
    return raw_path


DATABASE_FILE = resolve_runtime_path(os.environ.get("PERSONAL_AI_OS_DB"), "database.db")
DATABASE_PATH = str(DATABASE_FILE)
APP_TIMEZONE = os.environ.get("PERSONAL_AI_OS_TIMEZONE", "Asia/Kolkata")
IS_PRODUCTION = bool(os.environ.get("RENDER")) or os.environ.get("FLASK_ENV", "production").lower() == "production"
DEFAULT_SECRET_KEY = "personal-ai-os-dev-secret-change-me"

FLASK_CONFIG = {
    "PROPAGATE_EXCEPTIONS": False,
    "PERMANENT_SESSION_LIFETIME": timedelta(days=7),
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SAMESITE": "Lax",
    "SESSION_COOKIE_SECURE": IS_PRODUCTION,
    "REMEMBER_COOKIE_DURATION": timedelta(days=7),
    "REMEMBER_COOKIE_HTTPONLY": True,
    "REMEMBER_COOKIE_SAMESITE": "Lax",
    "REMEMBER_COOKIE_SECURE": IS_PRODUCTION,
    "TEMPLATES_AUTO_RELOAD": not IS_PRODUCTION,
}

MAX_CHAT_MESSAGES = 20
AI_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
SYSTEM_PROMPT = (
    "You are the helpful AI assistant inside Personal AI OS, a productivity dashboard. "
    "Give concise, practical, friendly answers that help the user plan, learn, and stay consistent. "
    "When the user asks for study help, tailor your suggestions using their current tasks, habits, and recent study history."
)
ENERGY_QUESTION_COUNT = 6
WORKOUT_CALORIE_RATES = {
    "Walking": 4,
    "Running": 10,
    "Gym": 6,
    "Jogging": 7,
    "Cycling": 8,
    "Swimming": 9,
    "Yoga": 4,
    "Stretching": 3,
    "Sports": 8,
    "Dancing": 6,
    "House Work": 4,
    "Climbing Stairs": 8,
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
CAREER_STATUSES = {"Applied", "In Progress", "Completed"}
