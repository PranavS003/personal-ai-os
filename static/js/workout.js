const workoutForm = document.getElementById("workoutForm");
const workoutType = document.getElementById("workoutType");
const workoutTypeGrid = document.getElementById("workoutTypeGrid");
const workoutDuration = document.getElementById("workoutDuration");
const workoutList = document.getElementById("workoutList");
const totalCaloriesText = document.getElementById("totalCaloriesText");
const workoutTypeButtons = Array.from(document.querySelectorAll("[data-activity-type]"));

function setWorkoutFeedback(message, isError = false) {
    window.personalAiDashboard?.setDashboardFeedback?.(message, isError);
}

function renderWorkoutList(state) {
    if (!workoutList || !totalCaloriesText || !state) {
        return;
    }

    const workouts = state.workouts || [];
    const workoutSummary = state.workout_summary || {
        total_calories: 0,
        total_minutes: 0,
        goal_minutes: 30,
    };

    totalCaloriesText.textContent = `${workoutSummary.total_calories} kcal burned today | ${workoutSummary.total_minutes} / ${workoutSummary.goal_minutes} min active`;

    if (!workouts.length) {
        workoutList.innerHTML = '<p class="setup-empty">No activity logged yet. Add a workout to start tracking calories.</p>';
        return;
    }

    workoutList.innerHTML = workouts.map((workout) => `
        <article class="workout-item">
            <strong>${workout.activity_type}</strong>
            <span>${workout.duration} min</span>
            <span>${workout.calories} kcal</span>
        </article>
    `).join("");
}

function setWorkoutType(value) {
    if (!workoutTypeButtons.length) {
        return;
    }

    const selectedValue = value || workoutTypeButtons[0].dataset.activityType || "Walking";

    if (workoutType) {
        workoutType.value = selectedValue;
    }

    workoutTypeButtons.forEach((button) => {
        const isActive = button.dataset.activityType === selectedValue;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
}

async function handleWorkoutSubmit(event) {
    event.preventDefault();

    const activityType = workoutType ? workoutType.value : "";
    const duration = Number(workoutDuration ? workoutDuration.value : 0);

    if (!duration) {
        setWorkoutFeedback("Please enter workout duration before adding activity.", true);
        return;
    }

    setWorkoutFeedback("Saving workout activity...");

    try {
        const response = await fetch("/add_workout", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                activity_type: activityType,
                duration,
            }),
        });
        const data = await response.json();

        if (!response.ok) {
            setWorkoutFeedback(data.error || "Could not save workout activity.", true);
            return;
        }

        if (workoutDuration) {
            workoutDuration.value = "";
        }

        window.personalAiDashboard?.renderDashboard?.(data.dashboard_state);
        setWorkoutFeedback("Workout activity added.");
    } catch (error) {
        setWorkoutFeedback("Could not reach the server. Please try again.", true);
    }
}

if (workoutForm) {
    workoutForm.addEventListener("submit", handleWorkoutSubmit);
}

if (workoutTypeGrid) {
    workoutTypeGrid.addEventListener("click", (event) => {
        const button = event.target.closest("[data-activity-type]");
        if (!button) {
            return;
        }

        setWorkoutType(button.dataset.activityType);
        setWorkoutFeedback("");
    });
}

document.addEventListener("personal-ai-os:dashboard-updated", (event) => {
    renderWorkoutList(event.detail);
});

setWorkoutType(workoutType ? workoutType.value : "Walking");
renderWorkoutList(window.personalAiDashboard?.getDashboardState?.());
