from datetime import timedelta

from utils.helpers import (
    format_progress_value,
    get_current_time,
    get_today_string,
    normalize_date_history,
    normalize_study_subjects,
    parse_iso_date,
)


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


def estimate_calorie_adjustment(weight_gap):
    gap = abs(float(weight_gap or 0))
    if gap < 2:
        return 300
    if gap < 6:
        return 400
    return 500


def build_health_guidance(health_snapshot):
    if not health_snapshot:
        return None

    bmi_value = float(health_snapshot.get("bmi") or 0)
    weight_kg = float(health_snapshot.get("weight_kg") or 0)
    ideal_min = float(health_snapshot.get("ideal_weight_min") or 0)
    ideal_max = float(health_snapshot.get("ideal_weight_max") or 0)
    category = health_snapshot.get("category") or get_bmi_category(bmi_value)

    if bmi_value < 18.5:
        calorie_delta = estimate_calorie_adjustment(ideal_min - weight_kg)
        guidance = {
            "goal": "Gain weight",
            "calorie_delta": calorie_delta,
            "calorie_direction": "increase",
            "calorie_guidance": f"Increase ~{calorie_delta} kcal/day to reach a healthier weight gradually.",
            "actions": [
                f"Increase calories by ~{calorie_delta}/day",
                "Eat protein-rich food",
                "Add strength training",
            ],
            "foods_to_add": ["Protein-rich meals", "Milk or yogurt", "Nuts and rice"],
            "foods_to_reduce": [],
            "short_tip": f"Tip: Increase ~{calorie_delta} kcal/day",
            "plan_slide": {
                "icon": "🧠",
                "text": f"Health Tip: Increase ~{calorie_delta} kcal/day and add strength training",
            },
        }
    elif bmi_value <= 24.9:
        guidance = {
            "goal": "Maintain",
            "calorie_delta": 0,
            "calorie_direction": "maintain",
            "calorie_guidance": "Maintain your current calories and stay active.",
            "actions": [
                "Follow a balanced diet",
                "Keep regular exercise",
            ],
            "foods_to_add": ["Fruits", "Vegetables", "Protein"],
            "foods_to_reduce": [],
            "short_tip": "Tip: Maintain your calories and regular exercise",
            "plan_slide": {
                "icon": "🧠",
                "text": "Health Tip: Keep a balanced diet and regular exercise",
            },
        }
    else:
        calorie_delta = estimate_calorie_adjustment(weight_kg - ideal_max)
        guidance = {
            "goal": "Lose weight",
            "calorie_delta": calorie_delta,
            "calorie_direction": "reduce",
            "calorie_guidance": f"Reduce ~{calorie_delta} kcal/day to reach ideal weight gradually.",
            "actions": [
                f"Reduce calories by ~{calorie_delta}/day",
                "Avoid junk food",
                "Add cardio like walking or jogging",
            ],
            "foods_to_add": ["Fruits", "Vegetables", "Protein"],
            "foods_to_reduce": ["Sugar", "Fried foods"],
            "short_tip": f"Tip: Reduce ~{calorie_delta} kcal/day",
            "plan_slide": {
                "icon": "🧠",
                "text": f"Health Tip: Reduce ~{calorie_delta} kcal/day and walk 20 min",
            },
        }

    return {
        **health_snapshot,
        **guidance,
    }


def calculate_health_insight(height_cm, weight_kg):
    height_m = height_cm / 100
    bmi_value = weight_kg / (height_m ** 2)
    ideal_min = 18.5 * (height_m ** 2)
    ideal_max = 24.9 * (height_m ** 2)

    return build_health_guidance({
        "height_cm": round(height_cm, 1),
        "weight_kg": round(weight_kg, 1),
        "bmi": round(bmi_value, 1),
        "category": get_bmi_category(bmi_value),
        "ideal_weight_min": round(ideal_min, 1),
        "ideal_weight_max": round(ideal_max, 1),
    })


def generate_start_day_plan(tasks, sleep_hours, mood, exercised):
    plan_parts = []

    if sleep_hours < 6:
        plan_parts.append("Take it easy today. Avoid heavy work.")

    if mood == "Stressed":
        plan_parts.append("Take breaks and avoid overload.")
    elif mood == "Low Energy":
        plan_parts.append("Start with light work, protect your focus, and build momentum gradually.")
    elif mood == "Focused":
        plan_parts.append("Use your focus early on the most important task.")

    if not exercised:
        plan_parts.append("Try a short walk today.")

    if tasks:
        plan_parts.append(f"Begin with {tasks[0]} and move through the rest one step at a time.")

    if not plan_parts:
        plan_parts.append("You are set up for a balanced day. Start with your top priority and keep your momentum steady.")

    return " ".join(plan_parts)


def generate_daily_plan(data):
    sleep_hours = float(data.get("sleep_hours") or 0)
    energy = int(data.get("energy_percent") or 0)
    pending_tasks = data.get("pending_tasks") or []
    completed_tasks = data.get("completed_tasks") or []
    study_hours = float(data.get("study_hours") or 0)
    exercise_minutes = int(data.get("exercise_minutes") or 0)
    calories_burned = int(data.get("calories_burned") or 0)
    current_hour = int(data.get("current_hour") or get_current_time().hour)
    health_data = data.get("health") or {}
    pipeline_focus = data.get("pipeline_focus") or {}
    remaining_study_hours = max(float(data.get("remaining_study_hours") or 0), 0)
    subjects_not_studied = normalize_study_subjects(data.get("subjects_not_studied") or [])

    suggestions = []
    company_name = str(pipeline_focus.get("company_name") or "").strip()
    role_name = str(pipeline_focus.get("role") or "").strip()
    next_action = str(pipeline_focus.get("next_action") or "").strip()

    if company_name and next_action:
        pipeline_label = company_name if not role_name else f"{company_name} {role_name}"
        suggestions.append(f"Prepare for {pipeline_label} (Next step: {next_action})")

    if remaining_study_hours > 0:
        remaining_text = format_progress_value(remaining_study_hours)
        hour_label = "hr" if abs(remaining_study_hours - 1) < 1e-9 else "hrs"
        suggestions.append(f"{remaining_text} {hour_label} remaining to reach today's study goal")

    if subjects_not_studied:
        suggestions.append(f"You haven't studied {subjects_not_studied[0]} today")

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

    health_tip = health_data.get("plan_slide")
    if health_tip:
        suggestions.append(health_tip)

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

    unique_suggestions = []
    seen = set()
    for suggestion in suggestions:
        if isinstance(suggestion, dict):
            suggestion_text = str(
                suggestion.get("text")
                or suggestion.get("title")
                or suggestion.get("label")
                or ""
            ).strip()
            normalized = suggestion_text.casefold() if suggestion_text else str(suggestion).casefold()
        else:
            suggestion_text = str(suggestion).strip()
            normalized = suggestion_text.casefold()

        if normalized in seen:
            continue
        seen.add(normalized)
        unique_suggestions.append(suggestion)

    return unique_suggestions[:4]
