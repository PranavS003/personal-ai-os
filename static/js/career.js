const careerState = window.careerState || {
    pipeline_entries: [],
    skill_focus: [],
    study: {
        today_hours: 0,
        weekly_total: 0,
        target_hours: 4,
        subject_catalog: [],
        subjects_studied_today: [],
    },
};

const pipelineForm = document.getElementById("pipelineForm");
const pipelineFormShell = document.getElementById("pipelineFormShell");
const togglePipelineFormButton = document.getElementById("togglePipelineForm");
const pipelineList = document.getElementById("pipelineList");
const skillList = document.getElementById("skillList");
const saveSkillsButton = document.getElementById("saveSkillsButton");
const studyForm = document.getElementById("studyForm");
const studyHoursInput = document.getElementById("studyHoursInput");
const targetHoursInput = document.getElementById("targetHoursInput");
const subjectInput = document.getElementById("subjectInput");
const addSubjectButton = document.getElementById("addSubjectButton");
const studySubjectChips = document.getElementById("studySubjectChips");
const studySubjectList = document.getElementById("studySubjectList");
const todayStudyValue = document.getElementById("todayStudyValue");
const weeklyStudyValue = document.getElementById("weeklyStudyValue");
const targetStudyValue = document.getElementById("targetStudyValue");
const careerFeedback = document.getElementById("careerFeedback");
const aiPrepResponse = document.getElementById("aiPrepResponse");
const aiPrepButtons = Array.from(document.querySelectorAll("[data-ai-prompt]"));

function formatHours(value) {
    const numericValue = Number(value || 0);
    if (Number.isInteger(numericValue)) {
        return `${numericValue}h`;
    }
    return `${numericValue.toFixed(1).replace(/\.0$/, "")}h`;
}

function normalizeSubject(value) {
    return String(value || "").trim();
}

function ensureStudyState() {
    const study = careerState.study || {};
    careerState.study = {
        today_hours: Number(study.today_hours || 0),
        weekly_total: Number(study.weekly_total || 0),
        target_hours: Number(study.target_hours || 4),
        subject_catalog: Array.isArray(study.subject_catalog) ? study.subject_catalog.slice() : [],
        subjects_studied_today: Array.isArray(study.subjects_studied_today) ? study.subjects_studied_today.slice() : [],
    };
}

function setFeedback(message, type = "") {
    if (!careerFeedback) {
        return;
    }

    careerFeedback.textContent = message || "";
    careerFeedback.className = "career-feedback";
    if (type) {
        careerFeedback.classList.add(type);
    }
}

function getStatusClass(status) {
    return String(status || "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
}

function syncState(nextState) {
    careerState.pipeline_entries = nextState.pipeline_entries || [];
    careerState.skill_focus = nextState.skill_focus || [];
    careerState.study = nextState.study || {
        today_hours: 0,
        weekly_total: 0,
        target_hours: 4,
        subject_catalog: [],
        subjects_studied_today: [],
    };
    renderCareerState();
}

function createElement(tagName, className, text) {
    const node = document.createElement(tagName);
    if (className) {
        node.className = className;
    }
    if (typeof text === "string") {
        node.textContent = text;
    }
    return node;
}

function setPipelineFormOpen(isOpen) {
    if (!pipelineFormShell) {
        return;
    }

    pipelineFormShell.classList.toggle("hidden", !isOpen);
    if (togglePipelineFormButton) {
        togglePipelineFormButton.textContent = isOpen ? "Close" : "Add Application";
    }
}

function renderPipeline() {
    if (!pipelineList) {
        return;
    }

    pipelineList.innerHTML = "";
    const entries = careerState.pipeline_entries || [];

    if (!entries.length) {
        pipelineList.appendChild(
            createElement("p", "empty-state", "No applications added yet. Add one to start tracking your pipeline.")
        );
        return;
    }

    entries.forEach((entry) => {
        const item = createElement("article", "career-list-item");
        const header = createElement("div", "career-list-header");
        const company = createElement("strong", "", entry.company_name);
        const status = createElement("span", `career-status ${getStatusClass(entry.status)}`, entry.status);
        header.append(company, status);

        const role = createElement("p", "career-meta", `Role: ${entry.role}`);
        const nextActionTitle = createElement("div", "career-row-title", "Next Action");
        const nextAction = createElement("p", "career-meta", entry.next_action);

        item.append(header, role, nextActionTitle, nextAction);
        pipelineList.appendChild(item);
    });
}

function buildSkillItem(skill) {
    const item = createElement("article", "skill-item");
    const labelRow = createElement("div", "skill-label-row");
    const name = createElement("span", "skill-name", skill.subject_name);
    const value = createElement("span", "skill-toggle-label", skill.studied_today ? "Studied Today" : "Not Studied");
    labelRow.append(name, value);

    const toggleRow = createElement("label", "skill-toggle-row");
    const helper = createElement("span", "skill-toggle-label", "Studied Today");
    const toggle = createElement("input", "skill-toggle");
    toggle.type = "checkbox";
    toggle.checked = Boolean(skill.studied_today);
    toggle.dataset.subjectName = skill.subject_name;
    toggle.addEventListener("change", (event) => {
        skill.studied_today = event.target.checked;
        value.textContent = event.target.checked ? "Studied Today" : "Not Studied";
        ensureStudyState();
        const nextSubjects = new Set(careerState.study.subjects_studied_today || []);
        if (event.target.checked) {
            nextSubjects.add(skill.subject_name);
        } else {
            nextSubjects.delete(skill.subject_name);
        }
        careerState.study.subjects_studied_today = Array.from(nextSubjects);
        renderStudySubjects();
    });
    toggleRow.append(helper, toggle);

    item.append(labelRow, toggleRow);
    return item;
}

function renderSkills() {
    if (!skillList) {
        return;
    }

    skillList.innerHTML = "";
    if (!careerState.skill_focus.length) {
        skillList.appendChild(createElement("p", "empty-state", "Add subjects in Study Tracker to see them here."));
        return;
    }

    careerState.skill_focus.forEach((skill) => {
        skillList.appendChild(buildSkillItem(skill));
    });
}

function renderStudySubjects() {
    if (studySubjectChips) {
        studySubjectChips.innerHTML = "";
    }
    if (studySubjectList) {
        studySubjectList.innerHTML = "";
    }

    const catalog = careerState.study.subject_catalog || [];
    const subjects = careerState.study.subjects_studied_today || [];

    if (!catalog.length) {
        const emptyChip = createElement("span", "study-subject-chip", "No subjects added");
        if (studySubjectChips) {
            studySubjectChips.appendChild(emptyChip);
        }
    } else {
        catalog.forEach((subject) => {
            if (studySubjectChips) {
                const chip = createElement("span", "study-subject-chip");
                const label = createElement("span", "", subject);
                const removeButton = createElement("button", "study-subject-remove", "x");
                removeButton.type = "button";
                removeButton.setAttribute("aria-label", `Remove ${subject}`);
                removeButton.addEventListener("click", () => {
                    careerState.study.subject_catalog = catalog.filter((item) => item !== subject);
                    careerState.study.subjects_studied_today = subjects.filter((item) => item !== subject);
                    careerState.skill_focus = careerState.skill_focus.filter((item) => item.subject_name !== subject);
                    renderCareerState();
                });
                chip.append(label, removeButton);
                studySubjectChips.appendChild(chip);
            }
        });
    }

    if (!subjects.length) {
        if (studySubjectList) {
            studySubjectList.appendChild(createElement("span", "study-subject-chip", "No study logged today"));
        }
        return;
    }

    subjects.forEach((subject) => {
        studySubjectList?.appendChild(createElement("span", "study-subject-chip", subject));
    });
}

function renderStudy() {
    ensureStudyState();
    const study = careerState.study;
    if (studyHoursInput) {
        studyHoursInput.value = study.today_hours || 0;
    }
    if (targetHoursInput) {
        targetHoursInput.value = study.target_hours || 4;
    }
    if (todayStudyValue) {
        todayStudyValue.textContent = formatHours(study.today_hours || 0);
    }
    if (weeklyStudyValue) {
        weeklyStudyValue.textContent = formatHours(study.weekly_total || 0);
    }
    if (targetStudyValue) {
        targetStudyValue.textContent = formatHours(study.target_hours || 4);
    }
    renderStudySubjects();
}

function renderCareerState() {
    renderPipeline();
    renderSkills();
    renderStudy();
}

function addSubjectToStudy(subjectValue) {
    const subject = normalizeSubject(subjectValue);
    if (!subject) {
        return false;
    }

    ensureStudyState();
    const catalog = new Set(careerState.study.subject_catalog || []);
    const exists = Array.from(catalog).some(
        (item) => item.toLowerCase() === subject.toLowerCase()
    );
    if (exists) {
        return false;
    }

    careerState.study.subject_catalog.push(subject);
    careerState.skill_focus.push({ subject_name: subject, studied_today: false });
    renderStudy();
    renderSkills();
    return true;
}

async function postJson(url, payload) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || "Something went wrong.");
    }
    return data;
}

pipelineForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    setFeedback("");

    const formData = new FormData(pipelineForm);
    try {
        const data = await postJson("/career/add_application", {
            company_name: formData.get("company_name"),
            role: formData.get("role"),
            status: formData.get("status"),
            next_action: formData.get("next_action"),
        });
        syncState(data.career_state || {});
        pipelineForm.reset();
        setPipelineFormOpen(false);
        setFeedback("Application added.", "success");
    } catch (error) {
        setFeedback(error.message, "error");
    }
});

saveSkillsButton?.addEventListener("click", async () => {
    setFeedback("");

    const subjectsStudied = Array.from(
        new Set(
            careerState.skill_focus
                .filter((skill) => skill.studied_today)
                .map((skill) => skill.subject_name)
        )
    );

    try {
        const data = await postJson("/career/update_skills", {
            subjects_studied: subjectsStudied,
        });
        syncState(data.career_state || {});
        setFeedback("Skill focus updated.", "success");
    } catch (error) {
        setFeedback(error.message, "error");
    }
});

togglePipelineFormButton?.addEventListener("click", () => {
    const nextIsHidden = pipelineFormShell?.classList.contains("hidden");
    setPipelineFormOpen(Boolean(nextIsHidden));
});

addSubjectButton?.addEventListener("click", () => {
    if (addSubjectToStudy(subjectInput?.value || "")) {
        subjectInput.value = "";
        subjectInput.focus();
        setFeedback("Subject added. Mark it in Skill Focus when you study it, then save.", "success");
    }
});

subjectInput?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") {
        return;
    }

    event.preventDefault();
    addSubjectButton?.click();
});

studyForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    setFeedback("");

    try {
        const data = await postJson("/career/update_study", {
            study_hours: studyHoursInput?.value || 0,
            target_hours: targetHoursInput?.value || 4,
            subjects_studied: careerState.study.subjects_studied_today || [],
            subject_catalog: careerState.study.subject_catalog || [],
        });
        syncState(data.career_state || {});
        if (subjectInput) {
            subjectInput.value = "";
        }
        setFeedback("Study tracker updated.", "success");
    } catch (error) {
        setFeedback(error.message, "error");
    }
});

aiPrepButtons.forEach((button) => {
    button.addEventListener("click", async () => {
        const prompt = button.dataset.aiPrompt || "";
        aiPrepResponse.textContent = "Preparing your prompt...";
        setFeedback("");

        try {
            const data = await postJson("/chat", { message: prompt });
            aiPrepResponse.textContent = data.reply || data.response || "Your prep prompt is ready.";
            setFeedback("AI prep started.", "success");
        } catch (error) {
            aiPrepResponse.textContent = "AI is unavailable right now. Use this as your next step: take 2 minutes to outline your answer, then practice it aloud once.";
            setFeedback("AI route was unavailable, so a fallback prompt was shown.", "error");
        }
    });
});

setPipelineFormOpen(false);
renderCareerState();
