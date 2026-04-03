const progressGrid = document.getElementById("progressGrid");
const motivationPanel = document.getElementById("motivationPanel");
const aiSuggestionsList = document.getElementById("aiSuggestionsList");
const taskProgressMeta = document.getElementById("taskProgressMeta");
const dailyTaskList = document.getElementById("dailyTaskList");
const dailyTaskMeta = document.getElementById("dailyTaskMeta");
const longTermTaskList = document.getElementById("longTermTaskList");
const longTermTaskMeta = document.getElementById("longTermTaskMeta");
const refreshDashboardButton = document.getElementById("refreshDashboard");
const resetDayButton = document.getElementById("resetDay");
const dashboardFeedback = document.getElementById("dashboardFeedback");
const vitalBars = document.getElementById("vitalBars");
const energyModal = document.getElementById("energyModal");
const energyQuestionList = document.getElementById("energyQuestionList");
const energyFeedback = document.getElementById("energyFeedback");
const submitEnergyCheckButton = document.getElementById("submitEnergyCheck");

const chatShell = document.getElementById("chatShell");
const chatWidget = document.getElementById("chatWidget");
const chatToggle = document.getElementById("chatToggle");
const chatClose = document.getElementById("chatClose");
const chatMessages = document.getElementById("chatMessages");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatSendButton = chatForm ? chatForm.querySelector("button") : null;
const chatSuggestions = Array.from(document.querySelectorAll("[data-chat-question]"));
const toggleTaskComposerButton = document.getElementById("toggleTaskComposer");
const quickTaskForm = document.getElementById("quickTaskForm");
const quickTaskInput = document.getElementById("quickTaskInput");
const quickTaskType = document.getElementById("quickTaskType");
const quickTaskPriority = document.getElementById("quickTaskPriority");
const healthForm = document.getElementById("healthForm");
const heightInput = document.getElementById("heightInput");
const weightInput = document.getElementById("weightInput");
const healthInsightResult = document.getElementById("healthInsightResult");

const energyQuestions = [
    "How many hours did you sleep?",
    "How focused do you feel right now?",
    "How physically active are you today?",
    "What is your current stress level?",
    "How strong is your motivation right now?",
    "How mentally fresh do you feel?"
];

const motivationMessages = [
    "Small focused actions build a powerful day.",
    "Clarity grows when you finish the next meaningful step.",
    "A steady rhythm beats a rushed sprint every time.",
    "Protect your energy, then put it where it matters most."
];

let dashboardState = window.dashboardState || null;
let energyAnswers = Array(energyQuestions.length).fill(0);

function setDashboardFeedback(message, isError = false) {
    if (!dashboardFeedback) {
        return;
    }

    dashboardFeedback.textContent = message;
    dashboardFeedback.classList.toggle("error", isError);
}

function setEnergyFeedback(message, isError = false) {
    if (!energyFeedback) {
        return;
    }

    energyFeedback.textContent = message;
    energyFeedback.classList.toggle("error", isError);
}

function createProgressRing({ percent = 0, mainValue = "0", unit = "", delay = 0 }) {
    return `
        <div class="progress-ring" data-progress="${percent}" data-delay="${delay}">
            <div class="progress-ring-inner">
                <strong>${mainValue}</strong>
                ${unit ? `<span class="ring-unit">${unit}</span>` : ""}
            </div>
        </div>
    `;
}

function getMetricMap(metrics = []) {
    return metrics.reduce((lookup, metric) => {
        lookup[metric.key] = metric;
        return lookup;
    }, {});
}

function getDailyMotivation(entryDate = "") {
    if (!entryDate) {
        return motivationMessages[0];
    }

    const seed = Array.from(entryDate).reduce((total, character) => total + character.charCodeAt(0), 0);
    return motivationMessages[seed % motivationMessages.length];
}

function createExerciseCaloriesCard(caloriesMetric, summary) {
    const exerciseMinutes = summary.exercise_minutes ?? 0;
    const caloriesBurned = summary.calories_burned ?? 0;

    return `
        <article class="life-card theme-calories">
            <div class="life-card-header life-card-toolbar">
                <div>
                    <p class="card-label">Movement</p>
                    <h3>Calories</h3>
                </div>
                <button type="button" class="metric-edit-button" data-metric-key="calories" data-current-value="${caloriesBurned}" aria-label="Update calories">Update</button>
            </div>
            ${createProgressRing({
                percent: caloriesMetric.percent,
                mainValue: `${caloriesBurned}`,
                unit: "kcal",
                delay: 0,
            })}
            <p class="ring-caption">Calories burned today</p>
            <p class="life-value">${caloriesMetric.value}</p>
            <p class="metric-note">Active time: ${exerciseMinutes} min</p>
        </article>
    `;
}

function createStudyCard(studyMetric, summary) {
    return `
        <article class="life-card theme-study study-card">
            <div class="life-card-header">
                <p class="card-label">Focus</p>
                <h3>Study Progress</h3>
            </div>
            ${createProgressRing({
                percent: studyMetric.percent,
                mainValue: `${summary.study_hours ?? 0}`,
                unit: "hrs",
                delay: 140,
            })}
            <p class="ring-caption">Logged study hours</p>
            <p class="life-value">${studyMetric.value}</p>
            <div class="study-actions">
                <button type="button" class="study-control-button" data-study-action="add" aria-label="Add study hour">+1 Hour</button>
                <button type="button" class="study-control-button secondary" data-study-action="remove" aria-label="Remove study hour">-1 Hour</button>
            </div>
        </article>
    `;
}

function renderMotivationCard(entryDate) {
    if (!motivationPanel) {
        return;
    }

    motivationPanel.innerHTML = `
        <article class="motivation-copy">
            <span class="motivation-icon" aria-hidden="true">?</span>
            <p class="motivation-line">${getDailyMotivation(entryDate)}</p>
        </article>
    `;
}

function createVitalBar(key, bar) {
    const isEnergy = key === "energy";
    const label = isEnergy ? "Energy Level" : "Sleep Tracker";
    const currentValue = isEnergy ? bar.percent : Number.parseFloat(bar.value) || 0;
    const energyTone = bar.percent >= 70 ? "high" : (bar.percent >= 40 ? "medium" : "low");
    const actionButton = isEnergy
        ? `<button type="button" class="metric-edit-button energy-recalc-button" id="openEnergyModal" aria-label="Calculate energy">Calculate Energy</button>`
        : `<button type="button" class="metric-edit-button" data-metric-key="${key}" data-current-value="${currentValue}" aria-label="Update ${label}">Update</button>`;

    return `
        <article class="vital-card theme-${key} ${isEnergy ? `energy-tone-${energyTone}` : ""}">
            <div class="vital-card-header life-card-toolbar">
                <div>
                    <p class="card-label">${isEnergy ? "Charge" : "Recovery"}</p>
                    <h3>${bar.emoji} ${label}</h3>
                </div>
                ${actionButton}
            </div>
            <div class="vital-bar-shell">
                <div class="vital-bar-track">
                    <div class="vital-bar-fill ${isEnergy ? `energy-fill-${energyTone}` : ""}" data-bar-fill="${key}" data-percent="${bar.percent}">
                        <span class="vital-bar-percent">${bar.percent}%</span>
                    </div>
                </div>
            </div>
            <div class="vital-bar-meta">
                <span>${bar.value}</span>
            </div>
        </article>
    `;
}

function renderSuggestions(suggestions) {
    if (!aiSuggestionsList) {
        return;
    }

    aiSuggestionsList.classList.remove("is-refreshing");
    void aiSuggestionsList.offsetWidth;
    aiSuggestionsList.classList.add("is-refreshing");

    if (!suggestions.length) {
        aiSuggestionsList.innerHTML = `
            <article class="suggestion-chip">
                <span class="suggestion-dot"></span>
                <p>Your AI plan will appear here as soon as today's dashboard data is available.</p>
            </article>
        `;
        return;
    }

    aiSuggestionsList.innerHTML = suggestions.map((suggestion) => `
        <article class="suggestion-chip">
            <span class="suggestion-dot"></span>
            <p>${suggestion}</p>
        </article>
    `).join("");
}

function renderProgressGrid(metrics, summary = {}) {
    if (!progressGrid) {
        return;
    }

    const metricMap = getMetricMap(metrics);
    const caloriesMetric = metricMap.calories || {
        percent: 0,
        value: "0 / 400 kcal",
    };
    const studyMetric = metricMap.study || {
        percent: 0,
        value: "0 / 4 hrs",
    };

    progressGrid.innerHTML = [
        createExerciseCaloriesCard(caloriesMetric, summary),
        createStudyCard(studyMetric, summary),
    ].join("");
    animateRings();
}

function renderVitalBars(bars) {
    if (!vitalBars) {
        return;
    }

    if (!bars?.sleep || !bars?.energy) {
        vitalBars.innerHTML = "";
        return;
    }

    vitalBars.innerHTML = `
        ${createVitalBar("sleep", bars.sleep)}
        ${createVitalBar("energy", bars.energy)}
    `;
    animateVitalBars();
}

function createDailyTaskCard(task) {
    return `
        <label class="task-tile ${task.completed ? "done" : ""}">
            <div class="task-tile-head">
                <div class="task-title-stack">
                    <p class="task-tile-title">${task.name}</p>
                    <span class="task-priority-badge priority-${(task.priority || "Medium").toLowerCase()}">${task.priority || "Medium"} Priority</span>
                </div>
                <input class="task-tile-toggle" type="checkbox" data-task-type="daily" data-task-name="${task.name}" ${task.completed ? "checked" : ""}>
            </div>
            <p class="task-tile-text">${task.completed ? "Completed and saved to today's progress." : "Open task for today's focus grid."}</p>
        </label>
    `;
}

function createLongTermTaskCard(task) {
    return `
        <label class="task-tile long-term-tile ${task.completed ? "done" : ""}">
            <div class="task-tile-head">
                <div class="task-title-stack">
                    <p class="task-tile-title">${task.name}</p>
                    <div class="task-pill-row">
                        <span class="task-priority-badge priority-${(task.priority || "Medium").toLowerCase()}">${task.priority || "Medium"} Priority</span>
                        <span class="task-streak-badge">🔥 ${task.streak_count || 0}</span>
                    </div>
                </div>
                <input class="task-tile-toggle" type="checkbox" data-task-type="long_term" data-task-id="${task.id}" data-task-name="${task.name}" ${task.completed ? "checked" : ""}>
            </div>
            <p class="task-tile-text">${task.completed ? "Completed today. Keep the streak alive tomorrow." : "Persistent goal tracked across days."}</p>
        </label>
    `;
}

function renderTaskLists(dailyTasks = [], longTermTasks = []) {
    if (!dailyTaskList || !longTermTaskList) {
        return;
    }

    const completedTasks = dailyTasks.filter((task) => task.completed).length;

    if (taskProgressMeta) {
        taskProgressMeta.textContent = dailyTasks.length
            ? `${completedTasks} of ${dailyTasks.length} daily tasks completed.`
            : "Use + Add Task to build today's checklist anytime.";
    }

    if (dailyTaskMeta) {
        dailyTaskMeta.textContent = dailyTasks.length
            ? `${completedTasks} completed, ${dailyTasks.length - completedTasks} left today.`
            : "No daily tasks yet.";
    }

    if (longTermTaskMeta) {
        const activeStreaks = longTermTasks.filter((task) => (task.streak_count || 0) > 0).length;
        longTermTaskMeta.textContent = longTermTasks.length
            ? `${longTermTasks.length} goals tracked, ${activeStreaks} with an active streak.`
            : "Add a long-term goal to start a streak.";
    }

    dailyTaskList.innerHTML = dailyTasks.length
        ? dailyTasks.map((task) => createDailyTaskCard(task)).join("")
        : '<p class="setup-empty">No tasks available for today.</p>';

    longTermTaskList.innerHTML = longTermTasks.length
        ? longTermTasks.map((task) => createLongTermTaskCard(task)).join("")
        : '<p class="setup-empty">No long-term goals added yet.</p>';
}

function renderEnergyStatus(energyCheck) {
    return;
}

function renderHealthInsight(health) {
    if (!healthInsightResult) {
        return;
    }

    if (heightInput && health?.height_cm) {
        heightInput.value = health.height_cm;
    }

    if (weightInput && health?.weight_kg) {
        weightInput.value = health.weight_kg;
    }

    if (!health) {
        healthInsightResult.innerHTML = `
            <article class="health-insight-card empty">
                <p>Enter height and weight to calculate BMI and your ideal weight range.</p>
            </article>
        `;
        return;
    }

    healthInsightResult.innerHTML = `
        <article class="health-insight-card">
            <div class="health-stat">
                <span class="health-label">BMI</span>
                <strong>${health.bmi}</strong>
                <span class="health-category">${health.category}</span>
            </div>
            <div class="health-range">
                <span class="health-label">Ideal Weight</span>
                <strong>${health.ideal_weight_min} - ${health.ideal_weight_max} kg</strong>
            </div>
        </article>
    `;
}

function broadcastDashboardUpdate(state) {
    document.dispatchEvent(new CustomEvent("personal-ai-os:dashboard-updated", { detail: state }));
}

function renderDashboard(state) {
    if (!state) {
        return;
    }

    dashboardState = state;
    renderSuggestions(state.suggestions || []);
    renderProgressGrid(state.metrics || [], state.summary || {});
    renderMotivationCard(state.entry_date || "");
    renderVitalBars(state.bars || {});
    renderTaskLists(state.daily_tasks || state.tasks || [], state.long_term_tasks || []);
    renderHealthInsight(state.health || null);
    broadcastDashboardUpdate(state);
}

function animateRing(ring) {
    const target = Number(ring.dataset.progress || 0);
    const delay = Number(ring.dataset.delay || 0);
    const start = performance.now() + delay;
    const duration = 900;

    function tick(now) {
        if (now < start) {
            requestAnimationFrame(tick);
            return;
        }

        const elapsed = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - elapsed, 3);
        ring.style.setProperty("--progress", `${Math.round(target * eased)}%`);

        if (elapsed < 1) {
            requestAnimationFrame(tick);
        }
    }

    ring.style.setProperty("--progress", "0%");
    requestAnimationFrame(tick);
}

function animateRings() {
    document.querySelectorAll(".progress-ring").forEach((ring) => animateRing(ring));
}

function animateVitalBars() {
    document.querySelectorAll("[data-bar-fill]").forEach((fill) => {
        fill.style.height = "0%";
        window.setTimeout(() => {
            fill.style.height = `${fill.dataset.percent}%`;
        }, 80);
    });
}

function renderEnergyQuestions() {
    if (!energyQuestionList) {
        return;
    }

    energyQuestionList.innerHTML = energyQuestions.map((question, index) => `
        <article class="energy-question-card">
            <p>${index + 1}. ${question}</p>
            <div class="energy-scale-row">
                <span>Very Low</span>
                ${[1, 2, 3, 4, 5].map((value) => `
                    <button
                        type="button"
                        class="energy-scale-button ${energyAnswers[index] === value ? "active" : ""}"
                        data-question-index="${index}"
                        data-score="${value}"
                    >
                        ${value}
                    </button>
                `).join("")}
                <span>Very High</span>
            </div>
        </article>
    `).join("");
}

function openEnergyModal() {
    if (!energyModal) {
        return;
    }

    renderEnergyQuestions();
    setEnergyFeedback("");
    energyModal.classList.remove("hidden");
    energyModal.setAttribute("aria-hidden", "false");
}

function closeEnergyModal() {
    if (!energyModal) {
        return;
    }

    energyModal.classList.add("hidden");
    energyModal.setAttribute("aria-hidden", "true");
}

async function fetchDashboardState() {
    const response = await fetch("/dashboard_data");
    const data = await response.json();

    if (!response.ok) {
        if (data.redirect_url) {
            window.location.href = data.redirect_url;
            return null;
        }
        throw new Error(data.error || "Could not load dashboard data.");
    }

    return data;
}

async function refreshDashboardState(showMessage = true) {
    try {
        const nextState = await fetchDashboardState();
        if (!nextState) {
            return;
        }

        renderDashboard(nextState);
        if (showMessage) {
            setDashboardFeedback("Dashboard refreshed.");
        }
    } catch (error) {
        setDashboardFeedback(error.message || "Could not refresh dashboard.", true);
    }
}

async function handleStudyAction(action, value = null) {
    setDashboardFeedback("Updating study hours...");

    try {
        const response = await fetch("/update_study", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, value })
        });
        const data = await response.json();

        if (!response.ok) {
            setDashboardFeedback(data.error || "Could not update study hours.", true);
            return;
        }

        renderDashboard(data.dashboard_state);
        setDashboardFeedback("Study hours updated.");
    } catch (error) {
        setDashboardFeedback("Could not reach the server. Please try again.", true);
    }
}

function toggleTaskComposer(forceOpen = null) {
    if (!quickTaskForm) {
        return;
    }

    const shouldOpen = forceOpen === null ? quickTaskForm.classList.contains("hidden-form") : forceOpen;
    quickTaskForm.classList.toggle("hidden-form", !shouldOpen);

    if (shouldOpen && quickTaskInput) {
        quickTaskInput.focus();
    }
}

async function handleQuickTaskSubmit(event) {
    event.preventDefault();

    const task = quickTaskInput ? quickTaskInput.value.trim() : "";
    const type = quickTaskType ? quickTaskType.value : "daily";
    const priority = quickTaskPriority ? quickTaskPriority.value : "Medium";

    if (!task) {
        setDashboardFeedback("Enter a task name before saving.", true);
        return;
    }

    setDashboardFeedback("Adding task...");

    try {
        const response = await fetch("/add_task", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task, priority, type }),
        });
        const data = await response.json();

        if (!response.ok) {
            setDashboardFeedback(data.error || "Could not add task.", true);
            return;
        }

        if (quickTaskInput) {
            quickTaskInput.value = "";
        }
        if (quickTaskPriority) {
            quickTaskPriority.value = "Medium";
        }
        if (quickTaskType) {
            quickTaskType.value = "daily";
        }

        renderDashboard(data.dashboard_state);
        toggleTaskComposer(false);
        setDashboardFeedback(type === "long_term" ? "Long-term goal added." : "Task added to today.");
    } catch (error) {
        setDashboardFeedback("Could not reach the server. Please try again.", true);
    }
}

async function handleMetricEdit(metricKey) {
    if (!dashboardState) {
        return;
    }

    const prompts = {
        sleep: { label: "sleep hours", placeholder: String(dashboardState.summary?.sleep_hours ?? 0) },
        energy: { label: "energy level (0-100)", placeholder: String(dashboardState.summary?.energy_percent ?? 0) },
        calories: { label: "calories burned", placeholder: String(dashboardState.summary?.calories_burned ?? 0) },
    };

    const config = prompts[metricKey];
    if (!config) {
        return;
    }

    const nextValue = window.prompt(`Enter updated ${config.label}:`, config.placeholder);
    if (nextValue === null) {
        return;
    }

    setDashboardFeedback(`Updating ${config.label}...`);

    try {
        const response = await fetch("/update_day_metric", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ metric: metricKey, value: nextValue }),
        });
        const data = await response.json();

        if (!response.ok) {
            setDashboardFeedback(data.error || "Could not update that metric.", true);
            return;
        }

        renderDashboard(data.dashboard_state);
        setDashboardFeedback("Daily metric updated.");
    } catch (error) {
        setDashboardFeedback("Could not reach the server. Please try again.", true);
    }
}

async function handleResetDay() {
    const confirmed = window.confirm("Reset today's active dashboard data and start fresh?");
    if (!confirmed) {
        return;
    }

    setDashboardFeedback("Resetting today...");

    try {
        const response = await fetch("/reset_day", { method: "POST" });
        const data = await response.json();

        if (!response.ok) {
            setDashboardFeedback(data.error || "Could not reset the day.", true);
            return;
        }

        document.body.classList.add("is-transitioning");
        window.setTimeout(() => {
            window.location.href = data.redirect_url || "/";
        }, 240);
    } catch (error) {
        setDashboardFeedback("Could not reach the server. Please try again.", true);
    }
}

async function handleTaskToggle(event) {
    const checkbox = event.target.closest("[data-task-name]");
    if (!checkbox) {
        return;
    }

    try {
        const response = await fetch("/toggle_task_status", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                task_id: checkbox.dataset.taskId,
                task_name: checkbox.dataset.taskName,
                type: checkbox.dataset.taskType || "daily",
                completed: checkbox.checked
            })
        });
        const data = await response.json();

        if (!response.ok) {
            checkbox.checked = !checkbox.checked;
            setDashboardFeedback(data.error || "Could not update task progress.", true);
            return;
        }

        renderDashboard(data.dashboard_state);
        setDashboardFeedback(
            checkbox.dataset.taskType === "long_term"
                ? "Long-term goal updated."
                : "Task progress updated."
        );
    } catch (error) {
        checkbox.checked = !checkbox.checked;
        setDashboardFeedback("Could not reach the server. Please try again.", true);
    }
}

async function handleEnergySubmit() {
    if (energyAnswers.some((answer) => answer < 1 || answer > 5)) {
        setEnergyFeedback(`Please answer all ${energyQuestions.length} questions before saving.`, true);
        return;
    }

    submitEnergyCheckButton.disabled = true;
    setEnergyFeedback("Saving your energy check...");

    try {
        const response = await fetch("/submit_energy", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ answers: energyAnswers })
        });
        const data = await response.json();

        if (!response.ok) {
            setEnergyFeedback(data.error || "Could not save your energy check.", true);
            return;
        }

        renderDashboard(data.dashboard_state);
        setDashboardFeedback(`Energy recalculated: ${data.energy_percent}%.`);
        closeEnergyModal();
    } catch (error) {
        setEnergyFeedback("Could not reach the server. Please try again.", true);
    } finally {
        submitEnergyCheckButton.disabled = false;
    }
}

async function handleHealthSubmit(event) {
    event.preventDefault();

    const heightCm = heightInput ? heightInput.value.trim() : "";
    const weightKg = weightInput ? weightInput.value.trim() : "";

    if (!heightCm || !weightKg) {
        setDashboardFeedback("Enter both height and weight to analyze health.", true);
        return;
    }

    setDashboardFeedback("Analyzing health insight...");

    try {
        const response = await fetch("/analyze_health", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ height_cm: heightCm, weight_kg: weightKg }),
        });
        const data = await response.json();

        if (!response.ok) {
            setDashboardFeedback(data.error || "Could not analyze health insight.", true);
            return;
        }

        if (data.dashboard_state) {
            renderDashboard(data.dashboard_state);
        } else {
            renderHealthInsight(data.health || null);
        }
        setDashboardFeedback("Health insight updated.");
    } catch (error) {
        setDashboardFeedback("Could not reach the server. Please try again.", true);
    }
}

function scrollChatToBottom() {
    if (!chatMessages) {
        return;
    }

    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendChatMessage(role, text, extraClass = "") {
    if (!chatMessages) {
        return null;
    }

    const message = document.createElement("div");
    message.className = `chat-message ${role} ${extraClass}`.trim();

    if (role === "bot") {
        const avatar = document.createElement("span");
        avatar.className = "chat-avatar chat-avatar-inline";
        avatar.setAttribute("aria-hidden", "true");
        message.appendChild(avatar);
    }

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";

    if (extraClass.includes("typing")) {
        bubble.innerHTML = '<span class="typing-indicator" aria-label="AI is typing"><span></span><span></span><span></span></span>';
    } else {
        bubble.textContent = text;
    }

    message.appendChild(bubble);
    chatMessages.appendChild(message);
    scrollChatToBottom();

    return message;
}

function setChatOpen(isOpen) {
    if (!chatWidget || !chatToggle) {
        return;
    }

    chatWidget.classList.toggle("hidden", !isOpen);
    chatShell?.classList.toggle("chat-open", isOpen);
    chatToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");

    if (isOpen && chatInput) {
        window.setTimeout(() => {
            scrollChatToBottom();
            chatInput.focus();
        }, 220);
    }
}

function setChatPending(isPending) {
    if (chatSendButton) {
        chatSendButton.disabled = isPending;
    }

    chatSuggestions.forEach((button) => {
        button.disabled = isPending;
    });
}

async function submitChatMessage(message) {
    if (!message) {
        return;
    }

    setChatOpen(true);
    appendChatMessage("user", message);

    const typingMessage = appendChatMessage("bot", "", "typing");
    setChatPending(true);

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message })
        });

        const data = await response.json();
        if (typingMessage) {
            typingMessage.remove();
        }

        if (!response.ok) {
            appendChatMessage("bot", data.error || "Something went wrong while talking to the AI.");
            return;
        }

        appendChatMessage("bot", data.response || data.reply || "I could not generate a response right now.");
    } catch (error) {
        if (typingMessage) {
            typingMessage.remove();
        }
        appendChatMessage("bot", "I could not reach the server. Please try again.");
    } finally {
        setChatPending(false);
        if (chatInput) {
            chatInput.focus();
        }
    }
}

async function triggerAiAction(message, buttonLabel = "") {
    if (!message) {
        return;
    }

    setChatOpen(true);

    if (buttonLabel) {
        appendChatMessage("user", buttonLabel);
    }

    const typingMessage = appendChatMessage("bot", "", "typing");
    setChatPending(true);

    try {
        const response = await fetch("/ai-action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message }),
        });
        const data = await response.json();

        if (typingMessage) {
            typingMessage.remove();
        }

        if (!response.ok) {
            appendChatMessage("bot", data.error || "The AI action is unavailable right now.");
            return;
        }

        appendChatMessage("bot", data.reply || data.response || "I could not generate a response right now.");
    } catch (error) {
        if (typingMessage) {
            typingMessage.remove();
        }
        appendChatMessage("bot", "I could not reach the AI action service. Please try again.");
    } finally {
        setChatPending(false);
        if (chatInput) {
            chatInput.focus();
        }
    }
}

async function sendChatMessage(event) {
    event.preventDefault();

    if (!chatInput) {
        return;
    }

    const message = chatInput.value.trim();
    if (!message) {
        return;
    }

    chatInput.value = "";
    await submitChatMessage(message);
}

window.personalAiDashboard = {
    getDashboardState: () => dashboardState,
    refreshDashboardState,
    renderDashboard,
    setDashboardFeedback,
    closeEnergyModal,
};

if (progressGrid) {
    progressGrid.addEventListener("click", (event) => {
        const metricButton = event.target.closest("[data-metric-key]");
        if (metricButton) {
            handleMetricEdit(metricButton.dataset.metricKey);
            return;
        }

        const button = event.target.closest("[data-study-action]");
        if (!button) {
            return;
        }

        handleStudyAction(button.dataset.studyAction, null);
    });
}

if (dailyTaskList) {
    dailyTaskList.addEventListener("change", handleTaskToggle);
}

if (longTermTaskList) {
    longTermTaskList.addEventListener("change", handleTaskToggle);
}

if (refreshDashboardButton) {
    refreshDashboardButton.addEventListener("click", () => refreshDashboardState(true));
}

if (resetDayButton) {
    resetDayButton.addEventListener("click", handleResetDay);
}

if (vitalBars) {
    vitalBars.addEventListener("click", (event) => {
        const metricButton = event.target.closest("[data-metric-key]");
        if (metricButton) {
            handleMetricEdit(metricButton.dataset.metricKey);
            return;
        }

        const button = event.target.closest("#openEnergyModal");
        if (!button) {
            return;
        }

        openEnergyModal();
    });
}

if (submitEnergyCheckButton) {
    submitEnergyCheckButton.addEventListener("click", handleEnergySubmit);
}

if (energyQuestionList) {
    energyQuestionList.addEventListener("click", (event) => {
        const button = event.target.closest("[data-score]");
        if (!button) {
            return;
        }

        const questionIndex = Number(button.dataset.questionIndex);
        const score = Number(button.dataset.score);
        energyAnswers[questionIndex] = score;
        renderEnergyQuestions();
        setEnergyFeedback("");
    });
}

document.querySelectorAll("[data-close-energy-modal]").forEach((button) => {
    button.addEventListener("click", closeEnergyModal);
});

if (chatToggle) {
    chatToggle.addEventListener("click", () => setChatOpen(true));
}

if (chatClose) {
    chatClose.addEventListener("click", () => setChatOpen(false));
}

if (chatForm) {
    chatForm.addEventListener("submit", sendChatMessage);
}

if (toggleTaskComposerButton) {
    toggleTaskComposerButton.addEventListener("click", () => {
        toggleTaskComposer();
        setDashboardFeedback("");
    });
}

if (quickTaskForm) {
    quickTaskForm.addEventListener("submit", handleQuickTaskSubmit);
}

if (healthForm) {
    healthForm.addEventListener("submit", handleHealthSubmit);
}

chatSuggestions.forEach((button) => {
    button.addEventListener("click", async () => {
        const quickMessage = button.dataset.chatQuestion || button.textContent.trim();
        if (button.dataset.aiAction) {
            await triggerAiAction(quickMessage, button.textContent.trim());
            return;
        }

        await submitChatMessage(button.dataset.chatQuestion || "");
    });
});

if (dashboardState) {
    renderDashboard(dashboardState);
}

scrollChatToBottom();
