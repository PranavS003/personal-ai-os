/* Modified: onboarding flow now uses a single-screen setup layout with
   compact quick-add chips, preserved skip preferences, and no page reload. */

const onboardingContext = window.onboardingContext || {};
const userKey = document.body.dataset.userKey || onboardingContext.userName || "default-user";
const storageKey = `personal-ai-os:intro-preferences:${userKey}`;
const autoSkipAttemptKey = `personal-ai-os:intro-auto-start:${userKey}`;

const dailySetupForm = document.getElementById("dailySetupForm");
const dailyTaskInput = document.getElementById("dailyTaskInput");
const addDailyTaskButton = document.getElementById("addDailyTask");
const dailyTaskList = document.getElementById("dailyTaskList");
const sleepHoursInput = document.getElementById("sleepHours");
const setupFeedback = document.getElementById("setupFeedback");
const startDayButton = document.getElementById("startDayButton");
const greetingHeading = document.getElementById("greetingHeading");
const suggestionGrid = document.getElementById("suggestionGrid");
const skipIntroButton = document.getElementById("skipIntroButton");
const skipIntroPreference = document.getElementById("skipIntroPreference");
const workoutTypeSetupGroup = document.getElementById("workoutTypeSetupGroup");
const setupWorkoutTypeGrid = document.getElementById("setupWorkoutTypeGrid");

const suggestionCards = [
    { label: "Study" },
    { label: "Travel" },
    { label: "Read" },
    { label: "Workout" },
];

const state = {
    tasks: [],
    mood: "",
    exercised: "",
    workoutType: "",
    sleepHours: "",
    skipIntro: false,
};

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function getSavedPreferences() {
    try {
        const raw = window.localStorage.getItem(storageKey);
        return raw ? JSON.parse(raw) : null;
    } catch (error) {
        return null;
    }
}

function savePreferences() {
    const payload = {
        tasks: state.tasks,
        mood: state.mood,
        exercised: state.exercised,
        workoutType: state.workoutType,
        sleepHours: state.sleepHours,
        skipIntro: state.skipIntro,
        updatedAt: Date.now(),
    };

    try {
        window.localStorage.setItem(storageKey, JSON.stringify(payload));
    } catch (error) {
        // Ignore localStorage issues and keep the UX working.
    }
}

function applySavedPreferences() {
    const saved = getSavedPreferences();
    if (!saved) {
        return;
    }

    state.tasks = Array.isArray(saved.tasks) ? [...saved.tasks] : [];
    state.mood = saved.mood || "";
    state.exercised = saved.exercised || "";
    state.workoutType = saved.workoutType || "";
    state.sleepHours = saved.sleepHours || "";
    state.skipIntro = Boolean(saved.skipIntro);

    if (sleepHoursInput && state.sleepHours) {
        sleepHoursInput.value = state.sleepHours;
    }

    if (skipIntroPreference) {
        skipIntroPreference.checked = state.skipIntro;
    }
}

function updateGreeting() {
    if (!greetingHeading) {
        return;
    }

    const hour = new Date().getHours();
    let partOfDay = "Morning";

    if (hour >= 12 && hour < 17) {
        partOfDay = "Afternoon";
    } else if (hour >= 17) {
        partOfDay = "Evening";
    }

    greetingHeading.textContent = `Good ${partOfDay}, ${onboardingContext.userName || "there"}`;
}

function renderSuggestionCards() {
    if (!suggestionGrid) {
        return;
    }

    suggestionGrid.innerHTML = suggestionCards.map((card) => {
        const isSelected = state.tasks.includes(card.label);
        return `
            <button
                type="button"
                class="quick-add-chip ${isSelected ? "active" : ""}"
                data-suggestion-task="${escapeHtml(card.label)}"
                aria-pressed="${isSelected ? "true" : "false"}"
            >
                <span class="quick-add-chip-label">${escapeHtml(card.label)}</span>
            </button>
        `;
    }).join("");
}

function renderDailyTasks() {
    if (!dailyTaskList) {
        return;
    }

    if (!state.tasks.length) {
        dailyTaskList.innerHTML = '<p class="setup-empty">Your selected tasks will appear here.</p>';
        return;
    }

    dailyTaskList.innerHTML = state.tasks.map((task, index) => `
        <div class="setup-task-chip">
            <span>${escapeHtml(task)}</span>
            <button type="button" class="setup-task-remove" data-task-index="${index}" aria-label="Remove ${escapeHtml(task)}">&times;</button>
        </div>
    `).join("");
}

function showFeedback(message, isError = false) {
    if (!setupFeedback) {
        return;
    }

    setupFeedback.textContent = message;
    setupFeedback.classList.toggle("error", isError);
}

function syncWorkoutVisibility() {
    const shouldShowWorkoutTypes = state.exercised === "yes";
    workoutTypeSetupGroup?.classList.toggle("hidden-panel", !shouldShowWorkoutTypes);

    if (!shouldShowWorkoutTypes) {
        state.workoutType = "";
        setupWorkoutTypeGrid?.querySelectorAll("[data-setup-workout-type]").forEach((button) => {
            button.classList.remove("active");
            button.setAttribute("aria-pressed", "false");
        });
        return;
    }

    if (!state.workoutType) {
        state.workoutType = "Walking";
    }

    setupWorkoutTypeGrid?.querySelectorAll("[data-setup-workout-type]").forEach((button) => {
        const isActive = button.dataset.setupWorkoutType === state.workoutType;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
}

function renderChoiceState(groupName, value) {
    document.querySelectorAll(`[data-choice-group="${groupName}"] .choice-button`).forEach((button) => {
        button.classList.toggle("active", button.dataset.value === value);
    });
}

function addTask(task) {
    const trimmedTask = (task || "").trim();
    if (!trimmedTask) {
        showFeedback("Add at least one task to start your day.", true);
        return;
    }

    if (state.tasks.includes(trimmedTask)) {
        showFeedback("That task is already in your list.", true);
        return;
    }

    state.tasks.push(trimmedTask);
    if (dailyTaskInput) {
        dailyTaskInput.value = "";
    }

    showFeedback("");
    renderSuggestionCards();
    renderDailyTasks();
    savePreferences();
}

function removeTask(index) {
    state.tasks.splice(index, 1);
    renderSuggestionCards();
    renderDailyTasks();
    savePreferences();
}

function toggleSuggestionTask(task) {
    if (state.tasks.includes(task)) {
        state.tasks = state.tasks.filter((item) => item !== task);
    } else {
        state.tasks.push(task);
    }

    renderSuggestionCards();
    renderDailyTasks();
    showFeedback("");
    savePreferences();
}

function setChoice(groupName, value) {
    renderChoiceState(groupName, value);

    if (groupName === "mood") {
        state.mood = value;
    } else if (groupName === "exercise") {
        state.exercised = value;
        syncWorkoutVisibility();
    }

    savePreferences();
}

function setWorkoutType(value) {
    state.workoutType = value;
    syncWorkoutVisibility();
    savePreferences();
}

function canSubmitCurrentState() {
    return Boolean(
        state.tasks.length &&
        state.sleepHours &&
        state.mood &&
        state.exercised &&
        (state.exercised !== "yes" || state.workoutType)
    );
}

async function submitCurrentState({ autoMode = false } = {}) {
    if (!canSubmitCurrentState()) {
        if (!autoMode) {
            showFeedback("Complete tasks, sleep, mood, and workout selection before continuing.", true);
        }
        return false;
    }

    startDayButton.disabled = true;
    showFeedback(autoMode ? "Applying saved setup and opening your dashboard..." : "Building your plan...");

    try {
        const response = await fetch("/submit_day_data", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                tasks: state.tasks,
                sleep_hours: state.sleepHours,
                mood: state.mood,
                exercised: state.exercised,
            })
        });
        const data = await response.json();

        if (!response.ok) {
            showFeedback(data.error || "Could not start your day. Please try again.", true);
            startDayButton.disabled = false;
            return false;
        }

        savePreferences();
        sessionStorage.removeItem(autoSkipAttemptKey);
        showFeedback(`Plan ready: ${data.plan}`);
        document.body.classList.add("is-transitioning");

        window.setTimeout(() => {
            window.location.href = data.redirect_url || "/dashboard";
        }, 220);

        return true;
    } catch (error) {
        showFeedback("Could not reach the server. Please try again.", true);
        startDayButton.disabled = false;
        return false;
    }
}

async function handleSubmit(event) {
    event.preventDefault();
    state.sleepHours = sleepHoursInput ? sleepHoursInput.value.trim() : state.sleepHours;
    savePreferences();
    await submitCurrentState();
}

async function handleSkip() {
    state.sleepHours = sleepHoursInput ? sleepHoursInput.value.trim() : state.sleepHours;
    state.skipIntro = Boolean(skipIntroPreference?.checked);
    savePreferences();

    if (canSubmitCurrentState()) {
        await submitCurrentState({ autoMode: true });
        return;
    }

    document.body.classList.add("intro-condensed");
    dailyTaskInput?.focus();
    showFeedback("Intro skipped. Complete any missing fields and start your day when ready.");
}

async function autoStartIfPreferred() {
    if (!state.skipIntro || !canSubmitCurrentState()) {
        return;
    }

    const attemptMarker = sessionStorage.getItem(autoSkipAttemptKey);
    if (attemptMarker) {
        return;
    }

    sessionStorage.setItem(autoSkipAttemptKey, "attempted");
    await submitCurrentState({ autoMode: true });
}

function hydrateUiFromState() {
    updateGreeting();
    renderChoiceState("mood", state.mood);
    renderChoiceState("exercise", state.exercised);
    syncWorkoutVisibility();
    renderSuggestionCards();
    renderDailyTasks();

    if (state.skipIntro) {
        document.body.classList.add("intro-condensed");
    }
}

addDailyTaskButton?.addEventListener("click", () => addTask(dailyTaskInput?.value || ""));

dailyTaskInput?.addEventListener("keypress", (event) => {
    if (event.key !== "Enter") {
        return;
    }

    event.preventDefault();
    addTask(dailyTaskInput.value);
});

dailyTaskList?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-task-index]");
    if (!button) {
        return;
    }

    removeTask(Number(button.dataset.taskIndex));
});

sleepHoursInput?.addEventListener("input", () => {
    state.sleepHours = sleepHoursInput.value.trim();
    savePreferences();
});

skipIntroPreference?.addEventListener("change", () => {
    state.skipIntro = skipIntroPreference.checked;
    document.body.classList.toggle("intro-condensed", state.skipIntro);
    savePreferences();
});

skipIntroButton?.addEventListener("click", handleSkip);

suggestionGrid?.addEventListener("click", (event) => {
    const card = event.target.closest("[data-suggestion-task]");
    if (!card) {
        return;
    }

    toggleSuggestionTask(card.dataset.suggestionTask);
});

document.querySelectorAll("[data-choice-group] .choice-button").forEach((button) => {
    button.addEventListener("click", () => {
        const group = button.closest("[data-choice-group]");
        if (!group) {
            return;
        }

        setChoice(group.dataset.choiceGroup, button.dataset.value);
        showFeedback("");
    });
});

setupWorkoutTypeGrid?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-setup-workout-type]");
    if (!button) {
        return;
    }

    setWorkoutType(button.dataset.setupWorkoutType);
});

dailySetupForm?.addEventListener("submit", handleSubmit);

applySavedPreferences();
hydrateUiFromState();
autoStartIfPreferred();
