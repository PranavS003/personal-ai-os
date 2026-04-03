const dailySetupForm = document.getElementById("dailySetupForm");
const dailyTaskInput = document.getElementById("dailyTaskInput");
const addDailyTaskButton = document.getElementById("addDailyTask");
const dailyTaskList = document.getElementById("dailyTaskList");
const sleepHoursInput = document.getElementById("sleepHours");
const setupFeedback = document.getElementById("setupFeedback");
const startDayButton = document.getElementById("startDayButton");

const dailyTasks = [];
let selectedMood = "";
let selectedExercise = "";

function renderDailyTasks() {
    if (!dailyTasks.length) {
        dailyTaskList.innerHTML = '<p class="setup-empty">Your tasks will appear here.</p>';
        return;
    }

    dailyTaskList.innerHTML = dailyTasks.map((task, index) => `
        <div class="setup-task-chip">
            <span>${task}</span>
            <button type="button" class="setup-task-remove" data-task-index="${index}" aria-label="Remove ${task}">&times;</button>
        </div>
    `).join("");
}

function showFeedback(message, isError = false) {
    setupFeedback.textContent = message;
    setupFeedback.classList.toggle("error", isError);
}

function addDailyTask() {
    const task = dailyTaskInput.value.trim();
    if (!task) {
        showFeedback("Add at least one task to start your day.", true);
        return;
    }

    if (dailyTasks.includes(task)) {
        showFeedback("That task is already in your list.", true);
        return;
    }

    dailyTasks.push(task);
    dailyTaskInput.value = "";
    showFeedback("");
    renderDailyTasks();
    dailyTaskInput.focus();
}

function setChoice(groupName, value) {
    const buttons = document.querySelectorAll(`[data-choice-group="${groupName}"] .choice-button`);
    buttons.forEach((button) => {
        button.classList.toggle("active", button.dataset.value === value);
    });

    if (groupName === "mood") {
        selectedMood = value;
    } else if (groupName === "exercise") {
        selectedExercise = value;
    }
}

async function submitDailySetup(event) {
    event.preventDefault();

    const sleepHours = sleepHoursInput.value.trim();
    if (!dailyTasks.length) {
        showFeedback("Please add at least one main task for today.", true);
        return;
    }

    if (!sleepHours) {
        showFeedback("Please enter how many hours you slept.", true);
        return;
    }

    if (!selectedMood) {
        showFeedback("Please choose your mood for today.", true);
        return;
    }

    if (!selectedExercise) {
        showFeedback("Please choose whether you exercised today.", true);
        return;
    }

    startDayButton.disabled = true;
    // The backend returns the plan text plus the dashboard redirect target.
    showFeedback("Building your plan...");

    try {
        const response = await fetch("/submit_day_data", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                tasks: dailyTasks,
                sleep_hours: sleepHours,
                mood: selectedMood,
                exercised: selectedExercise
            })
        });

        const data = await response.json();

        if (!response.ok) {
            showFeedback(data.error || "Could not start your day. Please try again.", true);
            startDayButton.disabled = false;
            return;
        }

        showFeedback(`Plan ready: ${data.plan}`);
        document.body.classList.add("is-transitioning");

        window.setTimeout(() => {
            window.location.href = data.redirect_url || "/dashboard";
        }, 260);
    } catch (error) {
        showFeedback("Could not reach the server. Please try again.", true);
        startDayButton.disabled = false;
    }
}

addDailyTaskButton.addEventListener("click", addDailyTask);

dailyTaskInput.addEventListener("keypress", (event) => {
    if (event.key === "Enter") {
        event.preventDefault();
        addDailyTask();
    }
});

dailyTaskList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-task-index]");
    if (!button) {
        return;
    }

    const index = Number(button.dataset.taskIndex);
    dailyTasks.splice(index, 1);
    renderDailyTasks();
});

document.querySelectorAll("[data-choice-group] .choice-button").forEach((button) => {
    button.addEventListener("click", () => {
        const group = button.closest("[data-choice-group]");
        setChoice(group.dataset.choiceGroup, button.dataset.value);
        showFeedback("");
    });
});

dailySetupForm.addEventListener("submit", submitDailySetup);

renderDailyTasks();
