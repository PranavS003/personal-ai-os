const workoutForm = document.getElementById("workoutForm");
const workoutType = document.getElementById("workoutType");
const workoutPicker = document.getElementById("workoutPicker");
const workoutDuration = document.getElementById("workoutDuration");
const workoutList = document.getElementById("workoutList");
const totalCaloriesText = document.getElementById("totalCaloriesText");
const selectedWorkoutBadge = document.getElementById("selectedWorkoutBadge");
const workoutPickerItems = Array.from(workoutPicker?.querySelectorAll("[data-activity-type]") || []);

let currentWorkoutIndex = 0;

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function setWorkoutFeedback(message, isError = false) {
    window.personalAiDashboard?.setDashboardFeedback?.(message, isError);
}

function renderWorkoutSummaryState(activityType = "") {
    if (!selectedWorkoutBadge) {
        return;
    }

    selectedWorkoutBadge.textContent = activityType || "Walking";
}

function getWrappedOffset(index, activeIndex, totalItems) {
    let offset = index - activeIndex;
    const half = Math.floor(totalItems / 2);

    if (offset > half) {
        offset -= totalItems;
    } else if (offset < -half) {
        offset += totalItems;
    }

    return offset;
}

function applyPickerItemState(item, offset) {
    const distance = Math.abs(offset);
    const isActive = offset === 0;
    const isVisible = distance <= 2;
    const translateY = offset * 40;
    const scale = isActive ? 1.08 : distance === 1 ? 0.94 : 0.88;
    const opacity = isActive ? 1 : distance === 1 ? 0.58 : distance === 2 ? 0.24 : 0;

    item.classList.toggle("active", isActive);
    item.classList.toggle("is-visible", isVisible);
    item.setAttribute("aria-selected", isActive ? "true" : "false");
    item.tabIndex = isActive ? 0 : -1;
    item.style.transform = `translateY(${translateY}px) scale(${scale})`;
    item.style.opacity = String(opacity);
    item.style.zIndex = String(10 - distance);
    item.style.pointerEvents = isVisible ? "auto" : "none";
}

function updateWorkoutPicker(index, { focusActive = false } = {}) {
    if (!workoutPickerItems.length) {
        return;
    }

    currentWorkoutIndex = (index + workoutPickerItems.length) % workoutPickerItems.length;
    const activeItem = workoutPickerItems[currentWorkoutIndex];
    const selectedValue = activeItem.dataset.activityType || "Walking";

    if (workoutType) {
        workoutType.value = selectedValue;
    }

    workoutPickerItems.forEach((item, itemIndex) => {
        const offset = getWrappedOffset(itemIndex, currentWorkoutIndex, workoutPickerItems.length);
        applyPickerItemState(item, offset);
    });

    renderWorkoutSummaryState(selectedValue);

    if (focusActive) {
        activeItem.focus({ preventScroll: true });
    }
}

function syncWorkoutPickerToValue(value, options = {}) {
    if (!workoutPickerItems.length) {
        return;
    }

    const nextIndex = workoutPickerItems.findIndex((item) => item.dataset.activityType === value);
    updateWorkoutPicker(nextIndex >= 0 ? nextIndex : 0, options);
}

function moveWorkoutPicker(direction) {
    updateWorkoutPicker(currentWorkoutIndex + direction);
}

function renderWorkoutList(state) {
    if (!workoutList || !totalCaloriesText || !state) {
        return;
    }

    const workouts = state.workouts || [];
    const totalMinutes = state.summary?.exercise_minutes ?? 0;
    const totalCalories = state.summary?.calories_burned ?? 0;
    const goalMinutes = 30;
    const latestWorkout = workouts[0]?.activity_type;

    totalCaloriesText.textContent = `${totalCalories} kcal burned today | ${totalMinutes} / ${goalMinutes} min active`;

    if (latestWorkout) {
        syncWorkoutPickerToValue(latestWorkout);
    }

    if (!workouts.length) {
        workoutList.innerHTML = '<p class="setup-empty">No workout logged yet. Pick an activity and add the time.</p>';
        return;
    }

    workoutList.innerHTML = workouts.map((workout) => `
        <article class="workout-item">
            <strong>${escapeHtml(workout.activity_type)}</strong>
            <span>${workout.duration} min</span>
            <span>${workout.calories} kcal</span>
        </article>
    `).join("");
}

async function handleWorkoutSubmit(event) {
    event.preventDefault();

    const activityType = workoutType ? workoutType.value : "";
    const duration = Number(workoutDuration ? workoutDuration.value : 0);

    if (!activityType) {
        setWorkoutFeedback("Choose a workout type first.", true);
        return;
    }

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
        setWorkoutFeedback(`${activityType} workout added.`);
    } catch (error) {
        setWorkoutFeedback("Could not reach the server. Please try again.", true);
    }
}

if (workoutForm) {
    workoutForm.addEventListener("submit", handleWorkoutSubmit);
}

if (workoutPicker) {
    workoutPicker.addEventListener("wheel", (event) => {
        event.preventDefault();
        moveWorkoutPicker(event.deltaY > 0 ? 1 : -1);
        setWorkoutFeedback("");
    }, { passive: false });

    workoutPicker.addEventListener("click", (event) => {
        const item = event.target.closest("[data-activity-type]");
        if (!item) {
            return;
        }

        syncWorkoutPickerToValue(item.dataset.activityType, { focusActive: true });
        setWorkoutFeedback("");
    });

    workoutPicker.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown") {
            event.preventDefault();
            moveWorkoutPicker(1);
            setWorkoutFeedback("");
            return;
        }

        if (event.key === "ArrowUp") {
            event.preventDefault();
            moveWorkoutPicker(-1);
            setWorkoutFeedback("");
        }
    });
}

document.addEventListener("personal-ai-os:dashboard-updated", (event) => {
    renderWorkoutList(event.detail);
});

syncWorkoutPickerToValue(workoutType ? workoutType.value : "Walking");
renderWorkoutList(window.personalAiDashboard?.getDashboardState?.());
