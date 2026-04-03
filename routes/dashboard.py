import json
import os

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime if the SDK is unavailable
    OpenAI = None

from flask import Blueprint, jsonify, request

from services import (
    OPENAI_MODEL,
    api_login_required,
    build_dashboard_state,
    extract_response_text,
    fetch_dashboard_stats,
    fetch_user_habits,
    fetch_user_tasks,
    get_chat_history,
    get_current_user,
    get_dashboard_context,
    get_db_connection,
    get_openai_reply,
    get_today_entry,
    trim_chat_history,
)

dashboard_bp = Blueprint("dashboard", __name__)

AI_ACTION_PROMPTS = {
    "energy": (
        "Give a short, practical energy reset for today. Include 3 or 4 concrete steps "
        "the user can do in the next 30 to 60 minutes."
    ),
    "evening": (
        "Create a simple evening routine that balances study and relaxation. "
        "Keep it calm, realistic, and easy to follow."
    ),
    "focus": (
        "Create a focused study plan for the rest of today. "
        "Use short work blocks, clear priorities, and one quick break suggestion."
    ),
}

AI_ACTION_FALLBACKS = {
    "energy": (
        "Try a quick reset: drink water, stand up and walk for 5 to 10 minutes, "
        "eat something light with protein, and do one small task before starting deeper work."
    ),
    "evening": (
        "Keep tonight simple: do one focused study block for 25 minutes, take a short break, "
        "finish one light review session, then wind down with music, stretching, or quiet screen-free time."
    ),
    "focus": (
        "Start with your most important subject for 25 minutes, take a 5-minute break, "
        "then do one more 25-minute block and finish by listing your next step for tomorrow."
    ),
}


def get_ai_action_prompt(action, dashboard_context):
    normalized_action = (action or "").strip().lower()
    base_prompt = AI_ACTION_PROMPTS.get(
        normalized_action,
        "Give a short, practical productivity response for today.",
    )

    return normalized_action, (
        f"{base_prompt}\n\n"
        "Keep the response concise, friendly, and actionable.\n\n"
        f"{dashboard_context}"
    )


def get_ai_action_fallback(action):
    return AI_ACTION_FALLBACKS.get(
        (action or "").strip().lower(),
        "Take one clear next step, keep your session short, and protect your energy with a short break after it.",
    )


@dashboard_bp.route("/add_task", methods=["POST"])
@api_login_required
def add_task():
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    task_name = (data.get("task") or "").strip()

    if not task_name:
        return jsonify({"error": "Task is required."}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO tasks (name, user) VALUES (?, ?)", (task_name, current_user))
    conn.commit()
    conn.close()

    return jsonify({"status": "success"})


@dashboard_bp.route("/tasks", methods=["GET"])
@api_login_required
def get_tasks():
    return jsonify(fetch_user_tasks())


@dashboard_bp.route("/delete_task/<int:task_id>", methods=["DELETE"])
@api_login_required
def delete_task(task_id):
    current_user = get_current_user()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = ? AND user = ?", (task_id, current_user))
    conn.commit()
    conn.close()

    return jsonify({"status": "deleted"})


@dashboard_bp.route("/add_habit", methods=["POST"])
@api_login_required
def add_habit():
    current_user = get_current_user()
    data = request.get_json(silent=True) or {}
    habit_name = (data.get("habit") or "").strip()

    if not habit_name:
        return jsonify({"error": "No habit provided"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO habits (habit, streak, user) VALUES (?, 0, ?)",
        (habit_name, current_user),
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Habit added"})


@dashboard_bp.route("/get_habits", methods=["GET"])
@api_login_required
def get_habits():
    return jsonify(fetch_user_habits())


@dashboard_bp.route("/update_streak/<int:habit_id>", methods=["POST"])
@api_login_required
def update_streak(habit_id):
    current_user = get_current_user()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE habits SET streak = streak + 1 WHERE id = ? AND user = ?",
        (habit_id, current_user),
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Streak updated"})


@dashboard_bp.route("/get_stats", methods=["GET"])
@api_login_required
def get_stats():
    return jsonify(fetch_dashboard_stats())


@dashboard_bp.route("/toggle_day_task", methods=["POST"])
@api_login_required
def toggle_day_task():
    current_user = get_current_user()
    today_entry = get_today_entry()
    if not today_entry:
        return jsonify({"error": "Please complete today's setup first."}), 400

    data = request.get_json(silent=True) or {}
    task_name = (data.get("task_name") or "").strip()
    completed = bool(data.get("completed"))

    if not task_name or task_name not in today_entry["tasks"]:
        return jsonify({"error": "Task not found for today."}), 404

    completed_tasks = set(today_entry["completed_tasks"])
    if completed:
        completed_tasks.add(task_name)
    else:
        completed_tasks.discard(task_name)

    filtered_completed_tasks = [
        task for task in today_entry["tasks"] if task in completed_tasks
    ]

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE daily_entries
        SET completed_tasks_json = ?
        WHERE user = ? AND entry_date = ?
        """,
        (json.dumps(filtered_completed_tasks), current_user, today_entry["entry_date"]),
    )
    conn.commit()
    conn.close()

    return jsonify(
        {
            "message": "Task progress updated.",
            "dashboard_state": build_dashboard_state(get_today_entry()),
        }
    )


@dashboard_bp.route("/chat", methods=["POST"])
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

    return jsonify({"reply": bot_reply, "messages": history})


@dashboard_bp.route("/ai-action", methods=["POST"])
def ai_action():
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").strip().lower()

    if not action:
        return jsonify({"error": "Action is required."}), 400

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return jsonify({"error": "OPENAI_API_KEY is not set on the server."}), 500

    dashboard_context = get_dashboard_context()
    normalized_action, prompt = get_ai_action_prompt(action, dashboard_context)

    if OpenAI is None:
        return jsonify({
            "action": normalized_action,
            "reply": get_ai_action_fallback(normalized_action),
            "fallback": True,
            "error": "OpenAI SDK is not installed on the server.",
        })

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are the AI assistant inside Personal AI OS. "
                        "Respond with helpful, short, practical guidance."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_output_tokens=220,
        )

        response_text = (getattr(response, "output_text", "") or "").strip()
        if not response_text:
            response_text = extract_response_text(response.model_dump())

        return jsonify({
            "action": normalized_action,
            "reply": response_text,
            "fallback": False,
        })
    except Exception as exc:  # pragma: no cover - depends on live API/runtime
        return jsonify({
            "action": normalized_action,
            "reply": get_ai_action_fallback(normalized_action),
            "fallback": True,
            "error": str(exc),
        })
