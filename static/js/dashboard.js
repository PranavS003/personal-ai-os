const progressGrid = document.getElementById("progressGrid");
const motivationPanel = document.getElementById("motivationPanel");
const aiSuggestionsList = document.getElementById("aiSuggestionsList");
const guidancePrevButton = document.getElementById("guidancePrev");
const guidanceNextButton = document.getElementById("guidanceNext");
const guidanceStep = document.getElementById("guidanceStep");
const guidanceDots = document.getElementById("guidanceDots");
const guidanceSlidesContainer = document.getElementById("guidanceSlides");
const streakValue = document.getElementById("streakValue");
const streakText = document.getElementById("streakText");
const skillSuggestionSlidesContainer = document.getElementById("skillSuggestionSlides");
const taskProgressMeta = document.getElementById("taskProgressMeta");
const dailyTaskList = document.getElementById("dailyTaskList");
const dailyTaskMeta = document.getElementById("dailyTaskMeta");
const longTermTaskList = document.getElementById("longTermTaskList");
const longTermTaskMeta = document.getElementById("longTermTaskMeta");
const refreshDashboardButton = document.getElementById("refreshDashboard");
const resetDayButton = document.getElementById("resetDay");
const dashboardFeedback = document.getElementById("dashboardFeedback");
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
const quickTaskForm = document.getElementById("quickTaskForm");
const quickTaskInput = document.getElementById("quickTaskInput");
const quickTaskType = document.getElementById("quickTaskType");
const quickTaskPriority = document.getElementById("quickTaskPriority");
const healthForm = document.getElementById("healthForm");
const heightInput = document.getElementById("heightInput");
const weightInput = document.getElementById("weightInput");
const healthInsightResult = document.getElementById("healthInsightResult");
const toggleInsightsButton = document.getElementById("toggleInsights");
const insightsBody = document.getElementById("insightsBody");
const dashboardHeroText = document.getElementById("dashboardHeroText");
const supportButton = document.getElementById("supportButton");
const supportPanel = document.getElementById("supportPanel");

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

let focusLabel = "Study";
let dashboardState = window.dashboardState || null;
let energyAnswers = Array(energyQuestions.length).fill(0);
let guidanceTips = [];
let currentGuidanceIndex = 0;
let guidanceTimer = null;
let skillSuggestions = [];
let currentSkillSuggestionIndex = 0;
let skillSuggestionTimer = null;
let supportHideTimer = null;

const GUIDANCE_ROTATION_MS = 5000;
const SKILL_ROTATION_MS = 5000;
const METRIC_TARGET_STORAGE_KEY = "personal-ai-os.metric-targets";
const DEFAULT_METRIC_TARGETS = Object.freeze({
    sleep: 8,
    study: 4,
    calories: 400,
});
const metricPickerStates = new Map();
const metricSaveTimers = new Map();
let metricTargets = loadMetricTargets();

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function setDashboardFeedback(message, isError = false) {
    if (!dashboardFeedback) {
        return;
    }

    dashboardFeedback.textContent = message;
    dashboardFeedback.classList.toggle("error", isError);
}

function setSupportPanelOpen(isOpen) {
    if (!supportButton || !supportPanel) {
        return;
    }

    supportPanel.classList.toggle("show", isOpen);
    supportButton.setAttribute("aria-expanded", isOpen ? "true" : "false");
    supportPanel.setAttribute("aria-hidden", isOpen ? "false" : "true");
}

function clearSupportHideTimer() {
    if (!supportHideTimer) {
        return;
    }

    window.clearTimeout(supportHideTimer);
    supportHideTimer = null;
}

function queueSupportHide() {
    clearSupportHideTimer();
    supportHideTimer = window.setTimeout(() => {
        if (!supportPanel?.matches(":hover") && !supportButton?.matches(":hover")) {
            setSupportPanelOpen(false);
        }
    }, 200);
}

function setEnergyFeedback(message, isError = false) {
    if (!energyFeedback) {
        return;
    }

    energyFeedback.textContent = message;
    energyFeedback.classList.toggle("error", isError);
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

function buildFallbackGuidance(state = {}) {
    const summary = state.summary || {};
    const pendingTasks = state.daily_tasks || state.tasks || [];
    const incompleteTasks = pendingTasks.filter((task) => !task.completed);
    const tips = [];

    if ((summary.sleep_hours ?? 0) < 6) {
        tips.push("Start with light study or planning");
    }
    if (incompleteTasks.length) {
        tips.push("Complete your pending tasks");
    }
    if ((summary.study_hours ?? 0) < 1) {
        tips.push(`${focusLabel} for 1 hour in focused sessions`);
    }
    if ((summary.exercise_minutes ?? 0) < 15) {
        tips.push("Take a short walk to refresh");
    }

    tips.push("Protect one calm block for your hardest task");
    return Array.from(new Set(tips));
}

function getPlanIcon(text = "", fallbackIcon = "\u2728") {
    const normalizedText = String(text || "").toLowerCase();

    if (["study", "learn", "concept", "class", "revision"].some((keyword) => normalizedText.includes(keyword))) {
        return "\uD83D\uDCD8";
    }
    if (["read", "reading", "pages", "review"].some((keyword) => normalizedText.includes(keyword))) {
        return "\uD83D\uDCD6";
    }
    if (["walk", "exercise", "workout", "active", "stretch"].some((keyword) => normalizedText.includes(keyword))) {
        return "\uD83C\uDFC3";
    }
    if (["plan", "planning", "priority", "schedule"].some((keyword) => normalizedText.includes(keyword))) {
        return "\uD83D\uDCCB";
    }
    if (["work", "task", "assignment", "focus", "project", "admin"].some((keyword) => normalizedText.includes(keyword))) {
        return "\uD83D\uDCBB";
    }
    if (["rest", "calm", "sleep", "wind down"].some((keyword) => normalizedText.includes(keyword))) {
        return "\uD83C\uDF19";
    }

    return fallbackIcon;
}

function normalizeGuidanceTip(tip) {
    if (tip && typeof tip === "object") {
        const text = String(tip.text || tip.title || "").trim();
        return {
            icon: tip.icon || getPlanIcon(text, "\uD83D\uDCA1"),
            text: text || "Protect one calm block for your hardest task",
        };
    }

    const text = String(tip || "").trim() || "Protect one calm block for your hardest task";
    return {
        icon: getPlanIcon(text, "\uD83D\uDCA1"),
        text,
    };
}

function getStreakDetails(state = {}) {
    const longTermTasks = state.long_term_tasks || [];
    const streakCount = longTermTasks.reduce((max, task) => Math.max(max, Number(task.streak_count) || 0), 0);

    if (streakCount >= 7) {
        return { count: streakCount, text: "Strong rhythm. Keep the chain alive" };
    }
    if (streakCount >= 3) {
        return { count: streakCount, text: "Consistency builds momentum" };
    }
    if (streakCount >= 1) {
        return { count: streakCount, text: "Small wins are stacking up" };
    }
    return { count: 0, text: "Start one small streak today" };
}

function buildSkillSuggestions(state = {}) {
    const dailyTasks = state.daily_tasks || state.tasks || [];
    const incompleteTasks = dailyTasks.filter((task) => !task.completed);
    const suggestions = [];

    if (incompleteTasks[0]?.name) {
        suggestions.push({ icon: getPlanIcon(incompleteTasks[0].name, "\uD83D\uDCBB"), text: incompleteTasks[0].name });
    }

    suggestions.push({ icon: "\uD83D\uDCD6", text: "Read 10 pages" });
    suggestions.push({ icon: "\uD83D\uDCBB", text: `Work on your ${focusLabel.toLowerCase()}` });
    suggestions.push({ icon: "\uD83D\uDCD8", text: "Learn a new concept" });

    if ((state.summary?.exercise_minutes ?? 0) < 15) {
        suggestions.push({ icon: "\uD83C\uDFC3", text: "Add a quick workout break" });
    }

    return suggestions.filter((item, index, items) => items.findIndex((entry) => entry.text === item.text) === index);
}

function buildPlanSlideMarkup(item, index, variant, isActive) {
    const textClass = variant === "skill" ? "skill-suggestion-text" : "guidance-text";
    const iconClass = variant === "skill" ? "skill-suggestion-icon" : "guidance-icon";
    const slideClass = variant === "skill" ? "skill-slide" : "guidance-slide";

    return `
        <article class="plan-slide ${slideClass} ${isActive ? "active" : ""}" data-slide-index="${index}" aria-hidden="${isActive ? "false" : "true"}">
            <span class="plan-slide-icon ${iconClass}" aria-hidden="true">${escapeHtml(item.icon)}</span>
            <p class="plan-slide-text ${textClass}">${escapeHtml(item.text)}</p>
        </article>
    `;
}

function renderGuidanceSlides() {
    if (!guidanceSlidesContainer) {
        return;
    }

    guidanceSlidesContainer.innerHTML = guidanceTips.map((tip, index) => {
        return buildPlanSlideMarkup(tip, index, "guidance", index === currentGuidanceIndex);
    }).join("");
}

function renderSkillSlides() {
    if (!skillSuggestionSlidesContainer) {
        return;
    }

    skillSuggestionSlidesContainer.innerHTML = skillSuggestions.map((suggestion, index) => {
        return buildPlanSlideMarkup(suggestion, index, "skill", index === currentSkillSuggestionIndex);
    }).join("");
}

function setActiveSlide(container, activeIndex) {
    if (!container) {
        return;
    }

    Array.from(container.children).forEach((slide, index) => {
        const isActive = index === activeIndex;
        slide.classList.toggle("active", isActive);
        slide.setAttribute("aria-hidden", isActive ? "false" : "true");
    });
}

function updateGuidanceDots() {
    if (!guidanceDots) {
        return;
    }

    guidanceDots.innerHTML = guidanceTips.map((_, index) => `
        <button
            type="button"
            class="guidance-dot ${index === currentGuidanceIndex ? "active" : ""}"
            data-guidance-index="${index}"
            aria-label="Go to guidance ${index + 1}"
        ></button>
    `).join("");
}

function showGuidanceTip(index) {
    if (!guidanceSlidesContainer || !guidanceStep || !guidanceTips.length) {
        return;
    }

    currentGuidanceIndex = (index + guidanceTips.length) % guidanceTips.length;
    guidanceStep.textContent = `Tip ${currentGuidanceIndex + 1}`;
    setActiveSlide(guidanceSlidesContainer, currentGuidanceIndex);
    updateGuidanceDots();
}

function resetGuidanceTimer() {
    if (guidanceTimer) {
        window.clearInterval(guidanceTimer);
    }

    if (guidanceTips.length < 2) {
        return;
    }

    guidanceTimer = window.setInterval(() => {
        showGuidanceTip(currentGuidanceIndex + 1);
    }, GUIDANCE_ROTATION_MS);
}

function showSkillSuggestion(index) {
    if (!skillSuggestionSlidesContainer || !skillSuggestions.length) {
        return;
    }

    currentSkillSuggestionIndex = (index + skillSuggestions.length) % skillSuggestions.length;
    setActiveSlide(skillSuggestionSlidesContainer, currentSkillSuggestionIndex);
}

function resetSkillSuggestionTimer() {
    if (skillSuggestionTimer) {
        window.clearInterval(skillSuggestionTimer);
    }

    if (skillSuggestions.length < 2) {
        return;
    }

    skillSuggestionTimer = window.setInterval(() => {
        showSkillSuggestion(currentSkillSuggestionIndex + 1);
    }, SKILL_ROTATION_MS);
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

function renderSuggestions(suggestions, state = {}) {
    if (!aiSuggestionsList) {
        return;
    }

    guidanceTips = (suggestions.length ? suggestions : buildFallbackGuidance(state)).map(normalizeGuidanceTip);
    currentGuidanceIndex = Math.min(currentGuidanceIndex, Math.max(guidanceTips.length - 1, 0));
    renderGuidanceSlides();

    if (guidanceTips.length) {
        showGuidanceTip(currentGuidanceIndex);
        resetGuidanceTimer();
    }

    if (guidancePrevButton) {
        guidancePrevButton.disabled = guidanceTips.length < 2;
    }
    if (guidanceNextButton) {
        guidanceNextButton.disabled = guidanceTips.length < 2;
    }

    const streak = getStreakDetails(state);
    if (streakValue) {
        streakValue.textContent = `\uD83D\uDD25 ${streak.count} Day${streak.count === 1 ? "" : "s"} Streak`;
    }
    if (streakText) {
        streakText.textContent = streak.text;
    }

    skillSuggestions = buildSkillSuggestions(state);
    currentSkillSuggestionIndex = Math.min(currentSkillSuggestionIndex, Math.max(skillSuggestions.length - 1, 0));
    renderSkillSlides();
    showSkillSuggestion(currentSkillSuggestionIndex);
    resetSkillSuggestionTimer();
}

function clampPercent(value) {
    return Math.max(0, Math.min(Number(value) || 0, 100));
}

function syncFocusLabel(nextLabel = "") {
    focusLabel = String(nextLabel || focusLabel || "Study").trim() || "Study";
    const focusLabelElement = document.getElementById("focusLabel");
    if (focusLabelElement) {
        focusLabelElement.innerText = focusLabel;
    }
}

function loadMetricTargets() {
    try {
        const rawTargets = window.localStorage.getItem(METRIC_TARGET_STORAGE_KEY);
        if (!rawTargets) {
            return { ...DEFAULT_METRIC_TARGETS };
        }

        const parsedTargets = JSON.parse(rawTargets);
        return {
            sleep: Number(parsedTargets.sleep) || DEFAULT_METRIC_TARGETS.sleep,
            study: Number(parsedTargets.study) || DEFAULT_METRIC_TARGETS.study,
            calories: Number(parsedTargets.calories) || DEFAULT_METRIC_TARGETS.calories,
        };
    } catch (error) {
        return { ...DEFAULT_METRIC_TARGETS };
    }
}

function saveMetricTargets() {
    try {
        window.localStorage.setItem(METRIC_TARGET_STORAGE_KEY, JSON.stringify(metricTargets));
    } catch (error) {
        // Ignore local storage issues.
    }
}

function getMetricConfig(metricKey, summary = {}) {
    const configs = {
        sleep: {
            key: "sleep",
            label: "Sleep",
            unit: "hrs",
            tone: "sleep",
            targetStep: 1,
            minTarget: 1,
            maxTarget: 24,
            valueStep: 1,
            rangeMin: 0,
            rangeMax: 24,
            summaryKey: "sleep_hours",
        },
        calories: {
            key: "calories",
            label: "Calories",
            unit: "kcal",
            tone: "calories",
            targetStep: 50,
            minTarget: 50,
            maxTarget: 2000,
            valueStep: 10,
            rangeMin: 0,
            rangeMax: Math.max(1000, (Number(summary.calories_burned) || 0) + 200, (Number(metricTargets.calories) || 0) + 200),
            summaryKey: "calories_burned",
        },
        study: {
            key: "study",
            label: focusLabel,
            unit: "hrs",
            tone: "study",
            targetStep: 1,
            minTarget: 1,
            maxTarget: 12,
            valueStep: 1,
            rangeMin: 0,
            rangeMax: 12,
            summaryKey: "study_hours",
        },
    };

    return configs[metricKey];
}

function formatMetricValue(metricKey, value) {
    const numericValue = Number(value) || 0;

    if (metricKey === "calories") {
        return String(Math.round(numericValue));
    }

    const roundedValue = Math.round(numericValue * 10) / 10;
    return Number.isInteger(roundedValue) ? String(roundedValue) : roundedValue.toFixed(1);
}

function getMetricCurrentValue(metricKey, summary = {}) {
    const config = getMetricConfig(metricKey, summary);
    if (!config) {
        return 0;
    }

    return Number(summary[config.summaryKey]) || 0;
}

function getMetricTargetValue(metricKey) {
    const config = getMetricConfig(metricKey, dashboardState?.summary || {});
    const fallbackTarget = DEFAULT_METRIC_TARGETS[metricKey] || 1;
    const storedTarget = Number(metricTargets[metricKey]);
    const nextTarget = Number.isFinite(storedTarget) ? storedTarget : fallbackTarget;

    return Math.max(config?.minTarget || 1, Math.min(nextTarget, config?.maxTarget || nextTarget));
}

function buildMetricPickerOptions(metricKey, currentValue, targetValue) {
    const config = getMetricConfig(metricKey, dashboardState?.summary || {});
    if (!config) {
        return [];
    }

    if (metricKey === "calories") {
        return [];
    }

    const options = [];
    for (let value = config.rangeMin; value <= config.rangeMax; value += config.valueStep) {
        options.push(value);
    }

    if (!options.includes(currentValue)) {
        options.push(currentValue);
    }

    if (!options.includes(targetValue)) {
        options.push(targetValue);
    }

    return Array.from(new Set(options))
        .map((value) => Number(value))
        .sort((left, right) => left - right);
}

function createMetricPickerMarkup(metricKey, options, currentValue) {
    return `
        <div class="metric-value-picker" data-metric-picker="${metricKey}" tabindex="0" aria-label="${escapeHtml(metricKey)} current value selector">
            ${options.map((option) => `
                <button
                    type="button"
                    class="metric-picker-item ${Number(option) === Number(currentValue) ? "active" : ""}"
                    data-picker-value="${escapeHtml(option)}"
                    aria-selected="${Number(option) === Number(currentValue) ? "true" : "false"}"
                >
                    ${escapeHtml(formatMetricValue(metricKey, option))}
                </button>
            `).join("")}
        </div>
    `;
}

function getMetricIdPrefix(metricKey) {
    return metricKey === "calories" ? "calorie" : metricKey;
}

function createMetricTargetControls(metricKey) {
    return `
        <div class="metric-adjust-controls">
            <button type="button" class="adjust-btn" onclick="updateTarget('${metricKey}', 1)" aria-label="Increase ${escapeHtml(metricKey)} target">+</button>
            <button type="button" class="adjust-btn" onclick="updateTarget('${metricKey}', -1)" aria-label="Decrease ${escapeHtml(metricKey)} target">-</button>
        </div>
    `;
}

function createInteractiveMetricCard(metricKey, summary = {}, delay = 0) {
    const config = getMetricConfig(metricKey, summary);
    const currentValue = getMetricCurrentValue(metricKey, summary);
    const targetValue = getMetricTargetValue(metricKey);
    const progressPercent = clampPercent((currentValue / targetValue) * 100);
    const pickerOptions = buildMetricPickerOptions(metricKey, currentValue, targetValue);
    const idPrefix = getMetricIdPrefix(metricKey);
    const showPicker = metricKey !== "calories";

    return `
        <article class="metric-target-card tone-${config.tone}" data-metric-card="${metricKey}">
            <div class="metric-card-head">
                <div>
                    <span class="metric-card-label">${metricKey === "study" ? `<span id="focusLabel">${escapeHtml(config.label)}</span>` : escapeHtml(config.label)}</span>
                    <strong class="metric-card-value" data-metric-value="${metricKey}">
                        <span id="${idPrefix}Current">${escapeHtml(formatMetricValue(metricKey, currentValue))}</span>
                        /
                        <span id="${idPrefix}Target">${escapeHtml(formatMetricValue(metricKey, targetValue))}</span>
                        ${escapeHtml(config.unit)}
                    </strong>
                </div>
            </div>
            <div class="metric-card-body">
                <div class="metric-ring-wrap">
                    <div class="progress-ring ring-${config.tone}" data-progress="${progressPercent}" data-delay="${delay}">
                        <div class="progress-ring-core">
                            <strong data-ring-text="${metricKey}">${escapeHtml(formatMetricValue(metricKey, currentValue))} / ${escapeHtml(formatMetricValue(metricKey, targetValue))}</strong>
                            <span>${escapeHtml(config.unit)}</span>
                        </div>
                    </div>
                    ${createMetricTargetControls(metricKey)}
                </div>
                ${showPicker ? `
                    <div class="metric-picker-panel">
                        <span class="metric-picker-label">Current</span>
                        ${createMetricPickerMarkup(metricKey, pickerOptions, currentValue)}
                    </div>
                ` : `
                    <div class="metric-picker-panel metric-picker-panel-static">
                        <span class="metric-picker-label">Current</span>
                        <p class="metric-static-note">Auto from workout log</p>
                    </div>
                `}
            </div>
        </article>
    `;
}

function createEnergyMetricCard(summary = {}, bars = {}) {
    const energyPercent = bars.energy?.percent ?? summary.energy_percent ?? 0;

    return `
        <button type="button" class="metric-target-card energy-metric-card" data-open-energy-modal="true" aria-label="Open energy check">
            <div class="metric-card-head">
                <div>
                    <span class="metric-card-label">Energy</span>
                    <strong class="metric-card-value">${escapeHtml(energyPercent)}%</strong>
                </div>
            </div>
            <div class="metric-card-body metric-card-body-compact">
                <div class="progress-ring ring-energy" data-progress="${clampPercent(energyPercent)}" data-delay="360">
                    <div class="progress-ring-core">
                        <strong>${escapeHtml(energyPercent)}%</strong>
                        <span>live</span>
                    </div>
                </div>
                <p class="metric-energy-note">Open the energy check to refresh your score.</p>
            </div>
        </button>
    `;
}

function setMetricSummaryValue(metricKey, value) {
    if (!dashboardState?.summary) {
        return;
    }

    if (metricKey === "sleep") {
        dashboardState.summary.sleep_hours = Number(value);
    } else if (metricKey === "study") {
        dashboardState.summary.study_hours = Number(value);
    } else if (metricKey === "calories") {
        dashboardState.summary.calories_burned = Number(value);
    }
}

function animateRingTo(ring, targetPercent, delay = 0, duration = 420) {
    if (!ring) {
        return;
    }

    const startTime = performance.now() + delay;
    const currentProgress = parseFloat(String(ring.style.getPropertyValue("--progress") || "0").replace("%", "")) || 0;
    const startValue = currentProgress;
    const finalValue = clampPercent(targetPercent);

    if (ring._progressAnimationFrame) {
        window.cancelAnimationFrame(ring._progressAnimationFrame);
    }

    function tick(now) {
        if (now < startTime) {
            ring._progressAnimationFrame = window.requestAnimationFrame(tick);
            return;
        }

        const elapsed = Math.min((now - startTime) / duration, 1);
        const eased = 1 - Math.pow(1 - elapsed, 3);
        const nextValue = startValue + ((finalValue - startValue) * eased);
        ring.style.setProperty("--progress", `${nextValue}%`);

        if (elapsed < 1) {
            ring._progressAnimationFrame = window.requestAnimationFrame(tick);
        }
    }

    ring._progressAnimationFrame = window.requestAnimationFrame(tick);
}

function updateMetricCardDisplay(metricKey) {
    if (!dashboardState?.summary || !progressGrid) {
        return;
    }

    const config = getMetricConfig(metricKey, dashboardState.summary);
    const currentValue = getMetricCurrentValue(metricKey, dashboardState.summary);
    const targetValue = getMetricTargetValue(metricKey);
    const progressPercent = clampPercent((currentValue / targetValue) * 100);
    const metricCard = progressGrid.querySelector(`[data-metric-card="${metricKey}"]`);
    const idPrefix = getMetricIdPrefix(metricKey);

    if (!metricCard) {
        return;
    }

    const valueLabel = metricCard.querySelector(`[data-metric-value="${metricKey}"]`);
    const ringText = metricCard.querySelector(`[data-ring-text="${metricKey}"]`);
    const ring = metricCard.querySelector(".progress-ring");
    const currentText = document.getElementById(`${idPrefix}Current`);
    const targetText = document.getElementById(`${idPrefix}Target`);

    if (currentText) {
        currentText.textContent = formatMetricValue(metricKey, currentValue);
    }

    if (targetText) {
        targetText.textContent = formatMetricValue(metricKey, targetValue);
    }

    if (valueLabel) {
        valueLabel.innerHTML = `
            <span id="${idPrefix}Current">${escapeHtml(formatMetricValue(metricKey, currentValue))}</span>
            /
            <span id="${idPrefix}Target">${escapeHtml(formatMetricValue(metricKey, targetValue))}</span>
            ${escapeHtml(config.unit)}
        `;
    }

    if (ringText) {
        ringText.textContent = `${formatMetricValue(metricKey, currentValue)} / ${formatMetricValue(metricKey, targetValue)}`;
    }

    if (ring) {
        ring.dataset.progress = String(progressPercent);
        animateRingTo(ring, progressPercent);
    }
}

function applyMetricPickerItemState(item, offset) {
    const distance = Math.abs(offset);
    const isActive = offset === 0;
    const isVisible = distance <= 2;
    const translateY = offset * 34;
    const scale = isActive ? 1.08 : distance === 1 ? 0.95 : 0.88;
    const opacity = isActive ? 1 : distance === 1 ? 0.54 : distance === 2 ? 0.2 : 0;

    item.classList.toggle("active", isActive);
    item.classList.toggle("is-visible", isVisible);
    item.setAttribute("aria-selected", isActive ? "true" : "false");
    item.tabIndex = isActive ? 0 : -1;
    item.style.transform = `translateY(${translateY}px) scale(${scale})`;
    item.style.opacity = String(opacity);
    item.style.pointerEvents = isVisible ? "auto" : "none";
}

function getPickerWrappedOffset(index, activeIndex, totalItems) {
    let offset = index - activeIndex;
    const half = Math.floor(totalItems / 2);

    if (offset > half) {
        offset -= totalItems;
    } else if (offset < -half) {
        offset += totalItems;
    }

    return offset;
}

function updateMetricPicker(metricKey, nextIndex, { persist = true, focusActive = false, syncSummary = true } = {}) {
    const pickerState = metricPickerStates.get(metricKey);
    if (!pickerState || !pickerState.items.length) {
        return;
    }

    pickerState.index = (nextIndex + pickerState.items.length) % pickerState.items.length;
    const nextValue = Number(pickerState.items[pickerState.index].dataset.pickerValue);

    pickerState.items.forEach((item, index) => {
        const offset = getPickerWrappedOffset(index, pickerState.index, pickerState.items.length);
        applyMetricPickerItemState(item, offset);
    });

    if (focusActive) {
        pickerState.items[pickerState.index].focus({ preventScroll: true });
    }

    if (syncSummary) {
        setMetricSummaryValue(metricKey, nextValue);
        updateMetricCardDisplay(metricKey);
    }

    if (persist) {
        queueMetricSave(metricKey, nextValue);
    }
}

function hydrateMetricPickers(summary = {}) {
    metricPickerStates.clear();

    progressGrid?.querySelectorAll("[data-metric-picker]").forEach((picker) => {
        const metricKey = picker.dataset.metricPicker;
        const items = Array.from(picker.querySelectorAll(".metric-picker-item"));
        const currentValue = getMetricCurrentValue(metricKey, summary);
        const activeIndex = Math.max(items.findIndex((item) => Number(item.dataset.pickerValue) === Number(currentValue)), 0);

        metricPickerStates.set(metricKey, { picker, items, index: activeIndex });
        updateMetricPicker(metricKey, activeIndex, { persist: false, focusActive: false, syncSummary: false });
    });
}

function queueMetricSave(metricKey, value) {
    const existingTimer = metricSaveTimers.get(metricKey);
    if (existingTimer) {
        window.clearTimeout(existingTimer);
    }

    const timeoutId = window.setTimeout(async () => {
        try {
            if (metricKey === "study") {
                const response = await fetch("/update_study", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ action: "edit", value }),
                });
                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || "Could not update study hours.");
                }

                renderDashboard(data.dashboard_state);
            } else {
                const response = await fetch("/update_day_metric", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ metric: metricKey, value }),
                });
                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || "Could not update that metric.");
                }

                renderDashboard(data.dashboard_state);
            }
        } catch (error) {
            setDashboardFeedback(error.message || "Could not save that metric.", true);
            refreshDashboardState(false);
        }
    }, 260);

    metricSaveTimers.set(metricKey, timeoutId);
}

function updateTarget(metricKey, change) {
    const config = getMetricConfig(metricKey, dashboardState?.summary || {});
    let nextTarget = getMetricTargetValue(metricKey);

    if (metricKey === "sleep") {
        nextTarget += change;
        if (nextTarget < 1) {
            nextTarget = 1;
        }
    } else if (metricKey === "study") {
        nextTarget += change;
        if (nextTarget < 1) {
            nextTarget = 1;
        }
    } else if (metricKey === "calories") {
        nextTarget += change * 50;
        if (nextTarget < 100) {
            nextTarget = 100;
        }
    } else {
        return;
    }

    nextTarget = Math.min(nextTarget, config.maxTarget);

    metricTargets = {
        ...metricTargets,
        [metricKey]: Number(nextTarget),
    };
    saveMetricTargets();
    updateMetricCardDisplay(metricKey);
}

window.updateTarget = updateTarget;

function renderProgressGrid(metrics, summary = {}, bars = {}) {
    if (!progressGrid) {
        return;
    }

    progressGrid.innerHTML = `
        <article class="metrics-compact-card metrics-interactive-card">
            <div class="metrics-ring-grid metrics-interactive-grid">
                ${createInteractiveMetricCard("sleep", summary, 0)}
                ${createInteractiveMetricCard("calories", summary, 120)}
                ${createInteractiveMetricCard("study", summary, 240)}
                ${createEnergyMetricCard(summary, bars)}
            </div>
        </article>
    `;

    hydrateMetricPickers(summary);
    syncFocusLabel(focusLabel);
}

function createDailyTaskCard(task) {
    return `
        <label class="task-tile task-compact-item ${task.completed ? "done" : ""}">
            <input class="task-tile-toggle compact-task-toggle" type="checkbox" data-task-type="daily" data-task-name="${escapeHtml(task.name)}" ${task.completed ? "checked" : ""}>
            <p class="task-tile-title task-compact-title">${escapeHtml(task.name)}</p>
        </label>
    `;
}

function createLongTermTaskCard(task) {
    return `
        <label class="task-tile task-compact-item long-term-tile ${task.completed ? "done" : ""}">
            <input class="task-tile-toggle compact-task-toggle" type="checkbox" data-task-type="long_term" data-task-id="${task.id}" data-task-name="${escapeHtml(task.name)}" ${task.completed ? "checked" : ""}>
            <p class="task-tile-title task-compact-title">${escapeHtml(task.name)}</p>
            <span class="task-streak-inline">&#128293; ${task.streak_count || 0} day${task.streak_count === 1 ? "" : "s"}</span>
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
            ? `${completedTasks}/${dailyTasks.length} done`
            : "";
    }

    if (dailyTaskMeta) {
        dailyTaskMeta.textContent = dailyTasks.length
            ? `${dailyTasks.length - completedTasks} left`
            : "";
    }

    if (longTermTaskMeta) {
        const activeStreaks = longTermTasks.filter((task) => (task.streak_count || 0) > 0).length;
        longTermTaskMeta.textContent = longTermTasks.length
            ? `${activeStreaks} active`
            : "";
    }

    dailyTaskList.innerHTML = dailyTasks.length
        ? dailyTasks.map((task) => createDailyTaskCard(task)).join("")
        : '<p class="setup-empty">No tasks yet.</p>';

    longTermTaskList.innerHTML = longTermTasks.length
        ? longTermTasks.map((task) => createLongTermTaskCard(task)).join("")
        : '<p class="setup-empty">No goals yet.</p>';
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
                <p>Enter height and weight to see your BMI and a quick health tip.</p>
            </article>
        `;
        return;
    }

    const categoryClass = String(health.category || "").toLowerCase().replace(/\s+/g, "-");
    const shortTip = health.short_tip || health.calorie_guidance || "Tip: Stay consistent with healthy habits";

    healthInsightResult.innerHTML = `
        <article class="health-insight-card">
            <div class="health-stat">
                <span class="health-label">BMI</span>
                <strong>${health.bmi}</strong>
            </div>
            <div class="health-range">
                <span class="health-label">Category</span>
                <span class="health-category ${escapeHtml(categoryClass)}">${escapeHtml(health.category)}</span>
            </div>
            <p class="health-tip-line">${escapeHtml(shortTip)}</p>
        </article>
    `;
}

function renderOverviewCards(state) {
    const summary = state?.summary || {};
    const totalTasks = summary.total_tasks ?? 0;
    const completedTasks = summary.completed_tasks ?? 0;
    const pendingTasks = summary.pending_tasks ?? Math.max(totalTasks - completedTasks, 0);

    if (dashboardHeroText) {
        dashboardHeroText.textContent = pendingTasks
            ? `${pendingTasks} task${pendingTasks === 1 ? "" : "s"} open today.`
            : "Tasks are clear for today.";
    }
}

function broadcastDashboardUpdate(state) {
    document.dispatchEvent(new CustomEvent("personal-ai-os:dashboard-updated", { detail: state }));
}

function renderDashboard(state) {
    if (!state) {
        return;
    }

    dashboardState = state;
    syncFocusLabel(state.focus_label || focusLabel);
    renderSuggestions(state.suggestions || [], state);
    renderProgressGrid(state.metrics || [], state.summary || {}, state.bars || {});
    renderMotivationCard(state.entry_date || "");
    renderTaskLists(state.daily_tasks || state.tasks || [], state.long_term_tasks || []);
    renderHealthInsight(state.health || null);
    renderOverviewCards(state);
    broadcastDashboardUpdate(state);
    window.requestAnimationFrame(() => animateRings());
}

function animateRing(ring) {
    const target = Number(ring.dataset.progress || 0);
    const delay = Number(ring.dataset.delay || 0);
    const hasAnimated = ring.dataset.animated === "true";

    if (!hasAnimated) {
        ring.style.setProperty("--progress", "0%");
    }

    animateRingTo(ring, target, delay, hasAnimated ? 420 : 900);
    ring.dataset.animated = "true";
}

function animateRings() {
    document.querySelectorAll(".progress-ring").forEach((ring) => animateRing(ring));
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
        setDashboardFeedback(type === "long_term" ? "Long-term goal added." : "Task added to today.");
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
    setFocusLabel: (nextLabel) => {
        syncFocusLabel(nextLabel);
        if (dashboardState) {
            renderDashboard(dashboardState);
        }
    },
    refreshDashboardState,
    renderDashboard,
    setDashboardFeedback,
    closeEnergyModal,
};

if (progressGrid) {
    progressGrid.addEventListener("click", (event) => {
        const pickerItem = event.target.closest(".metric-picker-item");
        if (pickerItem) {
            const picker = pickerItem.closest("[data-metric-picker]");
            if (!picker) {
                return;
            }

            const metricKey = picker.dataset.metricPicker;
            const pickerState = metricPickerStates.get(metricKey);
            if (!pickerState) {
                return;
            }

            const nextIndex = pickerState.items.findIndex((item) => item === pickerItem);
            if (nextIndex >= 0) {
                updateMetricPicker(metricKey, nextIndex, { focusActive: true });
            }
            return;
        }

        const energyTrigger = event.target.closest("[data-open-energy-modal]");
        if (energyTrigger) {
            openEnergyModal();
        }
    });

    progressGrid.addEventListener("wheel", (event) => {
        const picker = event.target.closest("[data-metric-picker]");
        if (!picker) {
            return;
        }

        event.preventDefault();
        const metricKey = picker.dataset.metricPicker;
        const pickerState = metricPickerStates.get(metricKey);
        if (!pickerState) {
            return;
        }

        updateMetricPicker(metricKey, pickerState.index + (event.deltaY > 0 ? 1 : -1));
    }, { passive: false });

    progressGrid.addEventListener("keydown", (event) => {
        const picker = event.target.closest("[data-metric-picker]");
        if (!picker) {
            return;
        }

        const metricKey = picker.dataset.metricPicker;
        const pickerState = metricPickerStates.get(metricKey);
        if (!pickerState) {
            return;
        }

        if (event.key === "ArrowDown") {
            event.preventDefault();
            updateMetricPicker(metricKey, pickerState.index + 1, { focusActive: true });
            return;
        }

        if (event.key === "ArrowUp") {
            event.preventDefault();
            updateMetricPicker(metricKey, pickerState.index - 1, { focusActive: true });
        }
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

if (guidancePrevButton) {
    guidancePrevButton.addEventListener("click", () => {
        showGuidanceTip(currentGuidanceIndex - 1);
        resetGuidanceTimer();
    });
}

if (guidanceNextButton) {
    guidanceNextButton.addEventListener("click", () => {
        showGuidanceTip(currentGuidanceIndex + 1);
        resetGuidanceTimer();
    });
}

if (aiSuggestionsList) {
    aiSuggestionsList.addEventListener("click", (event) => {
        const dot = event.target.closest("[data-guidance-index]");
        if (!dot) {
            return;
        }

        showGuidanceTip(Number(dot.dataset.guidanceIndex));
        resetGuidanceTimer();
    });
}

if (toggleInsightsButton && insightsBody) {
    toggleInsightsButton.addEventListener("click", () => {
        const isHidden = insightsBody.classList.toggle("hidden-panel");
        toggleInsightsButton.setAttribute("aria-expanded", isHidden ? "false" : "true");
        toggleInsightsButton.textContent = isHidden ? "Expand" : "Collapse";
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

if (quickTaskForm) {
    quickTaskForm.addEventListener("submit", handleQuickTaskSubmit);
}

if (healthForm) {
    healthForm.addEventListener("submit", handleHealthSubmit);
}

if (supportButton && supportPanel) {
    supportButton.addEventListener("click", () => {
        clearSupportHideTimer();
        setSupportPanelOpen(!supportPanel.classList.contains("show"));
    });

    supportButton.addEventListener("mouseenter", () => {
        clearSupportHideTimer();
        setSupportPanelOpen(true);
    });

    supportButton.addEventListener("mouseleave", () => {
        queueSupportHide();
    });

    supportPanel.addEventListener("mouseenter", () => {
        clearSupportHideTimer();
        setSupportPanelOpen(true);
    });

    supportPanel.addEventListener("mouseleave", () => {
        setSupportPanelOpen(false);
    });

    document.addEventListener("click", (event) => {
        if (supportButton.contains(event.target) || supportPanel.contains(event.target)) {
            return;
        }

        setSupportPanelOpen(false);
    });
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
