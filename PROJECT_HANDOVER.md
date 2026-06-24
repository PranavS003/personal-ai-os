# Personal AI OS - Complete Technical Handover Document

## 1. Project Overview

### Purpose
Personal AI OS is a monolithic Flask-based personal productivity web application that combines daily planning, task tracking, study tracking, workout logging, health insight generation, career preparation tracking, and AI-assisted productivity guidance in a single user-facing dashboard. The application is designed as a lightweight “personal operating system” for an individual user account, with support for multiple authenticated users backed by a shared SQLite database.

The project’s core idea is not just to store productivity data, but to translate that data into actionable recommendations and AI-assisted guidance. The application operationalizes a daily workflow that starts with onboarding/day setup, continues through dashboard execution, and is augmented by contextual AI features.

### Main Objectives
1. Provide a daily setup flow so a user can define tasks, sleep, mood, and exercise state for the day.
2. Maintain a living dashboard showing daily metrics, task progress, study progress, workouts, and health indicators.
3. Track both short-term daily tasks and long-term goals.
4. Integrate AI to provide contextual planning advice, conversational productivity support, and task-creation assistance.
5. Support a career-preparation area for applications, skills, and study-hours tracking.
6. Provide a visually polished mobile-first single-page-feeling UI, while still using server-rendered Flask templates.
7. Persist user data locally in SQLite with minimal infrastructure complexity.

### Target Users
- Individual users who want a personal productivity dashboard.
- Students preparing for exams, placements, or technical interviews.
- Users balancing daily planning, study tracking, workouts, and personal growth.
- Developers experimenting with personal productivity + AI assistant patterns.

### Core Functionality
- User registration, login, logout, and session-based authentication.
- Daily onboarding workflow to initialize a day plan.
- Dashboard with metrics for sleep, study, exercise, calories, and task completion.
- Task management for daily tasks and long-term goals.
- Habit tracking with streak counters.
- Study hour logging and updates.
- Workout logging with calorie estimation.
- Energy assessment via questionnaire and score persistence.
- Health insight calculations based on BMI and ideal weight ranges.
- Career page for application pipeline, skills, and study subjects/hours.
- Financial page with a mostly front-end-only prototype experience.
- AI chatbot for contextual assistant interactions.
- AI quick actions for energy, study, evening planning, and focus.

---

## 2. Technology Stack

### Languages
- Python: backend application, business logic, persistence logic, AI integration.
- HTML: server-rendered templates.
- CSS: all styling for auth pages, dashboard, career page, and financial page.
- JavaScript: client-side interactivity, SPA-like transitions, API calls, and UI rendering.
- SQL: implicit via SQLite DDL/DML embedded directly in `app.py`.

### Frameworks
- Flask: HTTP routing, request handling, templating integration, session handling.
- Flask-Login: user session management and `current_user` support.
- Jinja2: HTML templating via Flask.

### Libraries
Python dependencies from `requirements.txt`:
- `flask`
- `Flask-Login`
- `gunicorn`
- `python-dotenv`
- `openai`

Python standard library used heavily:
- `json`
- `importlib.util`
- `logging`
- `os`
- `sqlite3`
- `subprocess`
- `sys`
- `uuid`
- `dataclasses`
- `datetime`
- `functools`
- `pathlib`
- `zoneinfo`

Frontend/browser-side dependencies:
- No npm-based package management is present.
- Google Fonts loaded directly from CDN.
- No React/Vue/Svelte; all client logic is handwritten vanilla JavaScript.

### External Services
- Groq API, accessed through OpenAI-compatible SDK semantics using `base_url="https://api.groq.com/openai/v1"`.
- Google Fonts CDN.

### AI Services Used
- Groq-hosted LLM endpoint, called via the `openai` Python SDK.
- Default model from environment or fallback constant: `llama-3.3-70b-versatile`.
- AI usage patterns:
  - conversational assistant chat
  - quick-action assistant prompts
  - task-creation tool invocation pattern
  - dashboard-context-aware productivity guidance

---

## 3. Architecture

### High-Level System Architecture
This project is a classic server-rendered monolith with progressive enhancement.

Architecture layers:
1. Presentation layer:
   - Flask/Jinja HTML templates.
   - CSS for styling.
   - JavaScript for dynamic rendering and async API calls.
2. Application layer:
   - Flask route handlers in `app.py`.
   - embedded business rules and orchestration functions.
3. Persistence layer:
   - SQLite database file `database.db`.
4. AI integration layer:
   - OpenAI SDK client configured against Groq’s OpenAI-compatible endpoint.

There is no formal package/module separation. Almost the entire backend lives in a single file, `app.py`. This is the dominant architectural decision in the repository and heavily influences maintainability and extension strategy.

### Frontend Architecture
The frontend is template-driven and organized around three major experiences:
- onboarding flow
- dashboard/activity flow
- career and financial feature areas

Frontend characteristics:
- Server-rendered HTML for initial page load.
- JavaScript manages most state updates after the page is loaded.
- The dashboard behaves like a mini SPA inside `templates/index.html` with multiple page sections toggled in-place.
- Career and Financial also have separate page templates and partial component templates for SPA-like navigation or partial replacement.

Major frontend scripts:
- `static/js/dashboard.js`: primary dashboard controller and runtime state manager.
- `static/js/onboarding.js`: handles daily setup workflow.
- `static/js/workout.js`: workout-specific interaction logic.
- `static/js/career.js`: career feature interactions.
- `static/js/career_spa.js`: alternate/reusable career partial behavior for SPA transitions.
- `static/js/financial_spa.js`: purely front-end interactions for financial page prototype.
- `static/script.js`: small global UX helpers (modal closing, AI/chat visual tweaks).

### Backend Architecture
The backend is a single Flask app file containing:
- runtime dependency bootstrap
- configuration bootstrap
- logging setup
- database initialization and schema migration helpers
- authentication helpers
- domain/business logic
- AI prompt/tool orchestration
- all HTTP routes

Logical backend zones inside `app.py`:
1. Startup and dependency bootstrap.
2. Environment and Flask configuration.
3. Logging and exception handling.
4. User/session helpers.
5. Normalization/parsing helpers.
6. Health, streak, and productivity calculations.
7. Database schema management and migration helpers.
8. Daily-state accessors and derived-state builders.
9. Career domain helpers.
10. AI chat/session orchestration.
11. Flask route handlers.
12. Local development launcher.

### Database Architecture
Database engine: SQLite.

Database design characteristics:
- A single local database file: `database.db`.
- Mostly denormalized tables with user ownership represented by either `user` (username string) or `user_id` (integer), depending on feature area.
- Several tables store lists/history as JSON strings in TEXT columns rather than separate normalized relational tables.
- Migrations are implemented manually in Python using `CREATE TABLE IF NOT EXISTS`, `PRAGMA table_info`, and `ALTER TABLE` logic.
- The `daily_entries` table is central to the app’s day-scoped state.

### Data Flow Diagrams in Text Format

#### A. Daily Onboarding Flow
1. User opens `/`.
2. Backend checks `get_today_entry()`.
3. If no entry exists, backend renders `templates/onboarding.html`.
4. User submits daily tasks, sleep, mood, exercise via `static/js/onboarding.js`.
5. Frontend POSTs JSON to `/submit_day_data`.
6. Backend validates input, generates a start-day plan, upserts into `daily_entries`.
7. Backend syncs `tasks` records with `sync_today_task_records()`.
8. Frontend redirects to `/dashboard`.

#### B. Dashboard Refresh Flow
1. Dashboard page loads with server-provided `dashboard_state`.
2. `static/js/dashboard.js` hydrates UI from `window.dashboardState`.
3. User performs actions such as add task, toggle task, update study, log workout, submit energy.
4. Frontend sends fetch request to internal API endpoint.
5. Backend updates DB and returns fresh `dashboard_state`.
6. Frontend re-renders the dashboard from API response.

#### C. AI Chat Flow
1. User opens AI chat widget.
2. User submits text through `/chat`.
3. Backend assembles conversation history + dashboard context.
4. Backend decides whether explicit task creation intent exists.
5. If yes, backend enables function/tool schema `add_user_task` for model invocation.
6. LLM returns either plain response or tool call.
7. If tool call is present, backend validates arguments and inserts task.
8. Backend returns AI reply plus optional updated `dashboard_state`.
9. Frontend appends messages and re-renders dashboard if needed.

#### D. Career Study Flow
1. User opens `/career`.
2. Backend builds `career_state` from career tables.
3. Frontend displays study target, today’s subjects, weekly total, pipeline, and skills.
4. User submits study updates or application data.
5. Frontend POSTs to `/career/update_study`, `/career/add_application`, or `/career/update_skills`.
6. Backend validates, writes to tables, rebuilds `career_state`, and returns updated JSON.
7. Frontend updates rendered view.

---

## 4. Complete Folder Structure

### Repository Root
- `app.py`
  - Main Flask application.
  - Contains all backend logic, schema creation, business logic, AI integration, and routing.
  - This is the most important file in the project.
- `database.db`
  - SQLite database file.
  - Stores live application data.
- `.env`
  - Environment file used by `python-dotenv`.
  - Currently stores `GROQ_API_KEY`.
- `requirements.txt`
  - Python dependency manifest.
- `README.md`
  - Basic startup/setup instructions.
- `.gitignore`
  - Git exclusion rules.
- `__pycache__/`
  - Python bytecode cache.

### `templates/`
Contains all Jinja/HTML templates.

#### `templates/index.html`
Primary dashboard page. This is the main UI shell after onboarding. It includes:
- dashboard summary area
- task views
- workout module
- chat widget
- health form
- activity page section
- embedded page/tab containers
- references to `dashboard.js`

It is effectively the main application UI.

#### `templates/onboarding.html`
Daily setup page shown when the user has no active `daily_entries` row for the current date.
Handles:
- task list creation
- sleep-hours input
- mood selection
- exercise selection
- optional skip preference/autostart behavior

#### `templates/login.html`
Styled login form using POST to `/login`.

#### `templates/register.html`
Styled registration form using POST to `/register`.

#### `templates/career.html`
Standalone career page shell.
- loads career state via `window.careerState`
- includes career-specific UI
- includes bottom navigation
- loads `static/js/career.js`

#### `templates/financial.html`
Standalone financial page shell.
- includes `components/financial_content.html`
- includes bottom navigation
- loads `static/js/financial_spa.js`

### `templates/components/`
Reusable partial templates.

#### `templates/components/bottom_nav.html`
Bottom navigation bar used across pages.
Provides navigation affordance among dashboard/career/financial areas.

#### `templates/components/career_content.html`
The actual career page content partial. Used both in full-page render and partial render (`/career?partial=1`).
Contains:
- application pipeline
- skills matrix/toggles
- study tracker UI
- AI quick prep buttons

#### `templates/components/financial_content.html`
Financial feature content partial. Mostly static/prototype UI.
Contains:
- financial overview cards
- mock insight area
- expense logger form
- instruments tracker
- summary cards

### `static/`
Static client assets.

#### `static/css/`
- `style.css`
  - master/global stylesheet
  - auth styling, dashboard styling, chat styling, modal styling, activity layout, cards, metrics, and many utility visuals
- `career.css`
  - career-specific visual layer
- `financial.css`
  - financial-page specific visual layer

#### `static/js/`
- `dashboard.js`
  - master dashboard client controller
  - task CRUD interactions
  - chat UI and API usage
  - workout/dashboard synchronization
  - energy modal interactions
  - health form submission
  - navigation state management
  - rendering of metrics, suggestions, streaks, tasks, and AI panels
- `onboarding.js`
  - controls onboarding form state and submission
  - stores preferences in `localStorage`
  - supports auto-submit/skip behavior
- `workout.js`
  - manages workout picker carousel-like control and workout form submission
- `career.js`
  - manages career pipeline form, skill toggles, study subjects, study target, and AI prep actions
- `career_spa.js`
  - provides a page-initialization wrapper for career content when dynamically injected or re-initialized
- `financial_spa.js`
  - front-end-only dynamic messaging for the financial prototype

#### `static/images/`
- contains AI bot/illustration asset used by chatbot UI.

#### `static/script.js`
Global small script for modal behavior and welcome-bubble styling.

### How Files Interact
- `app.py` renders templates from `templates/`.
- Templates load CSS from `static/css/` and JS from `static/js/`.
- `dashboard.js`, `career.js`, `onboarding.js`, and `workout.js` call Flask JSON endpoints defined in `app.py`.
- `app.py` writes and reads SQLite data from `database.db`.
- AI responses are produced by backend functions in `app.py` and returned to dashboard UI.

---

## 5. Database Documentation

## Database Engine
- SQLite
- file path resolved from env `PERSONAL_AI_OS_DB` or default `database.db`

## Schema Management Strategy
The project uses runtime schema initialization and migration through `init_db()` and helper functions such as:
- `ensure_column()`
- `ensure_daily_entries_schema()`

This means schema evolution is embedded directly in application startup rather than maintained through Alembic or separate migration files.

## Tables

### `users`
Purpose: stores application accounts.

Fields:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `username TEXT NOT NULL UNIQUE`
- `email TEXT NOT NULL UNIQUE`
- `password_hash TEXT NOT NULL`
- `created_at TEXT NOT NULL`

Relationships:
- No foreign keys declared, but logical parent for most user-owned records.

Usage:
- authentication via email/password
- `Flask-Login` identity source

### `tasks`
Purpose: stores both daily tasks and long-term goals.

Fields:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `name TEXT`
- `user TEXT NOT NULL DEFAULT ''`
- `entry_date TEXT NOT NULL DEFAULT ''`
- `priority TEXT NOT NULL DEFAULT 'Medium'`
- `is_cleared INTEGER NOT NULL DEFAULT 0`
- `created_at TEXT`
- `user_id INTEGER`
- `task_type TEXT NOT NULL DEFAULT 'daily'`
- `completed INTEGER NOT NULL DEFAULT 0`
- `streak_count INTEGER NOT NULL DEFAULT 0`
- `last_completed_date TEXT`
- `completion_history_json TEXT NOT NULL DEFAULT '[]'`

Relationships:
- Logical relation to `users` by `user` and optionally `user_id`.
- No enforced foreign keys.

Notes:
- `task_type` differentiates `daily` vs `long_term`.
- Daily tasks are additionally represented inside `daily_entries.tasks_json`, so the system maintains duplication between summary JSON and normalized row storage.
- `completion_history_json` stores per-task completion dates as a JSON array.

### `study`
Purpose: legacy/general study-hour records.

Fields:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `subject TEXT`
- `hours INTEGER`
- `created_at TEXT`
- `user TEXT NOT NULL DEFAULT ''`

Relationships:
- Logical relation to `users` by `user`.

Notes:
- Appears partially legacy because career study tracking is handled more structurally in `career_study_tracker`.
- Still used by `/get_stats` and probably older study logging flow.

### `habits`
Purpose: stores habits and streak counts.

Observed schema behavior from code:
- original schema created `habit` and `streak`
- app later expects a `user` column and inserts with it
- therefore schema is migration-extended in `init_db()`

Core fields:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `habit TEXT`
- `streak INTEGER DEFAULT 0`
- `user TEXT` (added later through migration logic)

Relationships:
- Logical relation to `users` by `user`.

### `workouts`
Purpose: stores daily workout sessions.

Fields:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `user TEXT NOT NULL`
- `entry_date TEXT NOT NULL`
- `activity_type TEXT NOT NULL`
- `duration INTEGER NOT NULL`
- `calories INTEGER NOT NULL`
- `created_at TEXT NOT NULL`
- `is_cleared INTEGER NOT NULL DEFAULT 0`

Relationships:
- Logical relation to `users` by `user`.

Behavior:
- calories are estimated server-side using a static rate table.
- supports multiple workouts per day.

### `energy_logs`
Purpose: stores daily energy questionnaire result per user.

Fields:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `user_id INTEGER NOT NULL`
- `score INTEGER NOT NULL`
- `entry_date TEXT NOT NULL`
- `answers_json TEXT NOT NULL DEFAULT '[]'`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `UNIQUE(user_id, entry_date)`

Relationships:
- Logical relation to `users.id` via `user_id`.
- No foreign key constraint defined.

Behavior:
- one row per user per date
- stores both aggregate score and raw questionnaire answers

### `health_data`
Purpose: stores calculated health metrics for a user on a specific day.

Fields:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `user_id INTEGER NOT NULL`
- `entry_date TEXT NOT NULL`
- `height_cm REAL NOT NULL`
- `weight_kg REAL NOT NULL`
- `bmi REAL NOT NULL`
- `category TEXT NOT NULL`
- `ideal_weight_min REAL NOT NULL`
- `ideal_weight_max REAL NOT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `UNIQUE(user_id, entry_date)`

Relationships:
- Logical relation to `users.id` via `user_id`.

Behavior:
- one row per user per date
- records both inputs and derived metrics

### `daily_entries`
Purpose: central day-scoped state table.

Fields:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `user TEXT NOT NULL`
- `entry_date TEXT NOT NULL`
- `tasks_json TEXT NOT NULL`
- `sleep_hours REAL NOT NULL`
- `study_hours_total REAL NOT NULL DEFAULT 0`
- `mood TEXT NOT NULL`
- `energy_level INTEGER NOT NULL DEFAULT 0`
- `exercised INTEGER NOT NULL`
- `plan TEXT NOT NULL`
- `completed_tasks_json TEXT NOT NULL DEFAULT '[]'`
- `energy_percent INTEGER NOT NULL DEFAULT 0`
- `calories_override INTEGER`
- `energy_answers_json TEXT NOT NULL DEFAULT '[]'`
- `is_cleared INTEGER NOT NULL DEFAULT 0`
- `created_at TEXT NOT NULL`
- `UNIQUE(user, entry_date)`

Relationships:
- Logical relation to `users` by `user`.

Behavior:
- one active daily plan per user per date
- stores task list snapshot, mood, sleep, exercise, AI-generated plan, energy answers, and daily study total
- serves as the anchor for the dashboard

### `career_pipeline`
Purpose: tracks job/internship/application pipeline entries.

Fields:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `user TEXT NOT NULL`
- `company_name TEXT NOT NULL`
- `role TEXT NOT NULL`
- `status TEXT NOT NULL`
- `next_action TEXT NOT NULL`
- `created_at TEXT NOT NULL`

Relationships:
- Logical relation to `users` by `user`.

### `career_skill_focus`
Purpose: tracks skills being developed for career readiness.

Fields:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `user TEXT NOT NULL`
- `skill_name TEXT NOT NULL`
- `progress INTEGER NOT NULL DEFAULT 0`
- `updated_at TEXT NOT NULL`
- `UNIQUE(user, skill_name)`

Relationships:
- Logical relation to `users` by `user`.

### `career_study_tracker`
Purpose: stores per-day placement/career-related study tracking.

Fields:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `user TEXT NOT NULL`
- `entry_date TEXT NOT NULL`
- `study_hours REAL NOT NULL DEFAULT 0`
- `target_hours REAL NOT NULL DEFAULT 4`
- `subjects_json TEXT NOT NULL DEFAULT '[]'`
- `updated_at TEXT NOT NULL`
- `UNIQUE(user, entry_date)`

Relationships:
- Logical relation to `users` by `user`.

### `career_subjects`
Purpose: catalog of study subjects relevant to the user’s career preparation.

Fields:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `user TEXT NOT NULL`
- `subject_name TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `UNIQUE(user, subject_name)`

Relationships:
- Logical relation to `users` by `user`.

## Relationships Summary
This database is mostly soft-linked rather than relationally enforced.

Logical relationships:
- `users.id` -> `energy_logs.user_id`
- `users.id` -> `health_data.user_id`
- `users.username` -> `tasks.user`
- `users.username` -> `daily_entries.user`
- `users.username` -> `study.user`
- `users.username` -> `habits.user`
- `users.username` -> `workouts.user`
- `users.username` -> `career_pipeline.user`
- `users.username` -> `career_skill_focus.user`
- `users.username` -> `career_study_tracker.user`
- `users.username` -> `career_subjects.user`

## Database Data Flow

### Daily setup write path
`/submit_day_data` -> `daily_entries` upsert -> `sync_today_task_records()` -> `tasks`

### Task completion path
`/toggle_day_task` -> `tasks.completed`, `tasks.streak_count`, `tasks.last_completed_date`, `tasks.completion_history_json` -> `daily_entries.completed_tasks_json`

### Study path
- dashboard/general flow: `daily_entries.study_hours_total`
- legacy aggregate flow: `study`
- career-specific flow: `career_study_tracker`, `career_subjects`

### Health path
`/analyze_health` -> `health_data`

### Energy path
`/submit_energy` -> `energy_logs` + `daily_entries.energy_percent` + `daily_entries.energy_answers_json`

### Workout path
`/add_workout` -> `workouts`

---

## 6. Feature Documentation

### 6.1 Authentication
Implemented via Flask-Login.

Internal flow:
- Registration validates username/email/password constraints and uniqueness.
- Passwords are hashed with `generate_password_hash`.
- Login uses `check_password_hash` against `users.password_hash`.
- Flask session stores authenticated user state.
- App also explicitly stores some session values such as `chat_session_id` and `last_onboarding_date`.

Dependencies:
- `users` table
- Flask secret key
- Flask-Login `login_manager`

### 6.2 Daily Onboarding / Day Initialization
Purpose: set up the day before dashboard use.

Inputs:
- tasks
- sleep_hours
- mood
- exercised

Internal mechanics:
- frontend maintains a local temporary task list
- user submits JSON to `/submit_day_data`
- backend validates all values
- backend generates a human-readable plan with `generate_start_day_plan()`
- backend upserts the user’s row in `daily_entries`
- backend synchronizes task rows in `tasks`
- frontend redirects to dashboard

Design rationale:
- The app enforces a daily initialization ritual as a core product pattern.
- This simplifies dashboard assumptions because downstream features can assume `today_entry` exists.

### 6.3 Dashboard Rendering
Purpose: present current-day operational state.

Generated through:
- server-side `build_dashboard_state(today_entry)`
- client-side re-render in `dashboard.js`

State includes:
- suggestions / dynamic plan
- metrics
- task lists
- workout summary
- streak display
- study summary
- health insight
- career-related context slices

Dependencies:
- `daily_entries`
- `tasks`
- `workouts`
- `career_*`
- `health_data`
- `energy_logs`

### 6.4 Task Management
Two task categories:
- daily
- long_term

Internal behavior:
- `POST /add_task` inserts new tasks.
- Daily tasks update both `daily_entries.tasks_json` and normalized `tasks` rows.
- Long-term goals live directly in `tasks` with `task_type='long_term'`.
- `GET /tasks` lists active tasks.
- `DELETE /delete_task/<id>` soft-clears or removes task linkage from day state.
- `/toggle_day_task` or `/toggle_task_status` updates completion state and streak metadata.

Important implementation detail:
- Daily tasks are duplicated across `daily_entries.tasks_json` and `tasks`. The sync helper is responsible for keeping these aligned.
- This is a key maintenance hotspot.

### 6.5 Habit Tracking
Endpoints:
- `/add_habit`
- `/get_habits`
- `/update_streak/<habit_id>`

Behavior:
- simple CRUD-lite implementation
- increments only upward
- no date-awareness and no reset logic in current design

Limitations:
- weaker feature maturity than tasks/workouts/study
- does not integrate into the main dashboard state as deeply as tasks

### 6.6 Study Tracking
There are multiple study subsystems:
1. daily dashboard study total in `daily_entries.study_hours_total`
2. legacy `study` table
3. career-specific study tracker in `career_study_tracker`

Dashboard study operations:
- `/log_study_progress` adds hours to today’s running total
- `/update_study` modifies hours by action/value semantics

Career study operations:
- `/career/update_study` stores career study hours, target, and studied subjects

Design note:
- Study tracking is functionally useful but structurally fragmented.
- Future refactor should unify these three representations.

### 6.7 Workout Logging
Inputs:
- activity type
- duration in minutes

Internal behavior:
- `WORKOUT_CALORIE_RATES` maps workout type to calories-per-minute estimate
- `/add_workout` validates type and duration
- backend computes calories = rate * duration
- inserts into `workouts`
- dashboard refreshes totals for calories and exercise minutes

Supported types include:
- Walking
- Running
- Gym
- Jogging
- Cycling
- Swimming
- Yoga
- Stretching
- Sports
- Dancing
- House Work
- Climbing Stairs

### 6.8 Energy Assessment
Purpose: quantify current energy via a six-question modal.

Questions cover:
- sleep
- focus
- physical activity
- stress
- motivation
- mental freshness

Flow:
- frontend collects answers
- POST to `/submit_energy`
- backend validates answers and computes percent/score
- writes to both `energy_logs` and `daily_entries`
- dashboard uses the value as a metric and in dynamic planning

### 6.9 Health Insight / BMI Analysis
Inputs:
- height_cm
- weight_kg

Internal calculation:
- BMI
- BMI category
- ideal weight range
- estimated calorie adjustment
- health guidance object

Core helpers:
- `calculate_health_insight()`
- `build_health_guidance()`
- `get_bmi_category()`
- `estimate_calorie_adjustment()`

Persisted in:
- `health_data`

### 6.10 Career Pipeline
Purpose: track job applications and related actions.

Entities:
- company name
- role
- status
- next action

Statuses supported:
- `Applied`
- `In Progress`
- `Completed`

Endpoints:
- `/career/add_application`
- `/career/update_skills`
- `/career/update_study`

View model built by:
- `build_career_state(user)`

### 6.11 Career Skill Focus
Purpose: track progress across career skills.

Behavior:
- user toggles/updates skill progress on frontend
- backend upserts skills into `career_skill_focus`
- used to derive focus recommendations

### 6.12 Career Subject Catalog
Purpose: maintain set of study subjects for placement/career prep.

Behavior:
- supplied from study updates
- saved in `career_subjects`
- used to compare studied vs not-yet-studied subjects in dashboard planning logic

### 6.13 AI Chatbot
Purpose: contextual assistant within dashboard.

Behavior:
- stores transient chat history per session in memory, not DB
- builds dashboard-aware prompts
- supports task creation through tool semantics when user explicitly asks
- returns concise practical guidance

State containers:
- `CHAT_SESSIONS = {}`
- `PENDING_AI_TASKS = {}`

Important note:
- memory is ephemeral and process-local
- restarting the app clears all chat memory
- horizontal scaling would break session continuity unless externalized

### 6.14 AI Quick Actions
Configured quick prompts:
- energy
- study
- evening
- focus

Behavior:
- frontend triggers `/ai-action`
- backend injects dashboard context and user message
- model returns concise answer
- backend returns safe fallback text if AI unavailable

### 6.15 Financial Page
Current implementation is mostly a front-end prototype.

Implemented behavior:
- static financial cards
- rotating advice insight on button click
- expense form validation and local feedback only

Not implemented server-side:
- actual persistence of expenses
- real financial analytics
- authenticated financial data model

This section should be treated as UI scaffolding rather than a fully backed feature.

---

## 7. API Documentation

All APIs are internal Flask endpoints returning HTML or JSON.

## Authentication Model
- HTML routes use `@login_required`.
- JSON routes generally use `@api_login_required`.
- Session-cookie based auth, no token auth.

## HTML Routes

### `GET|POST /login`
- GET: render login form
- POST form fields:
  - `email`
  - `password`
- Success: redirect to `/`
- Failure: re-render with error

### `GET|POST /register`
- GET: render register form
- POST form fields:
  - `username`
  - `email`
  - `password`
- Success: create user, sign in, redirect to `/`
- Failure: re-render with validation error

### `GET /logout`
- Clears chat session state and user auth session.
- Redirects to `/login`.

### `GET /`
- Requires login.
- If today entry exists -> redirect `/dashboard`
- Else render onboarding page.

### `GET /dashboard`
- Requires login.
- Renders main dashboard with embedded state.

### `GET /career`
- Requires login.
- `?partial=1` returns partial template only.

### `GET /financial`
- Requires login.
- `?partial=1` returns partial template only.

## JSON Routes

### `POST /career/add_application`
Request JSON:
- `company_name: string`
- `role: string`
- `status: string`
- `next_action: string`

Response JSON:
- `message`
- `career_state`

Validation:
- non-empty strings
- status must belong to allowed set

### `POST /career/update_skills`
Request JSON:
- likely array/object of skills and progress values

Response JSON:
- `message`
- `career_state`

### `POST /career/update_study`
Request JSON:
- `study_hours`
- `target_hours`
- `subjects_studied`
- `subject_catalog`

Response JSON:
- `message`
- `career_state`

### `POST /add_task`
Request JSON:
- `task: string`
- `priority: High|Medium|Low`
- `type: daily|long_term`

Response JSON:
- `message`
- `dashboard_state`

Errors:
- missing task
- unsupported task type
- missing daily setup for daily tasks
- duplicate task/goal

### `GET /tasks`
Response JSON array of tasks:
- `id`
- `name`
- `priority`
- `entry_date`
- `type`
- `completed`
- `streak_count`
- `last_completed_date`

### `DELETE /delete_task/<task_id>`
Deletes or clears a task for the current user.
Response JSON typically:
- `message`
- `dashboard_state`

### `POST /add_habit`
Request JSON:
- `habit`

Response JSON:
- `message`

### `GET /get_habits`
Response JSON:
- raw rows from `habits`

### `POST /update_streak/<habit_id>`
Response JSON:
- `message`

### `GET /get_stats`
Response JSON:
- `tasks`
- `study_hours`
- `habits`

### `GET /dashboard_data`
Response JSON:
- complete dashboard state
- or 404 with `redirect_url`

### `POST /log_study_progress`
Request JSON:
- `subject`
- `hours`

Response JSON:
- `message`
- `dashboard_state`

### `POST /update_study`
Request JSON:
- `action`
- `value`

Response JSON:
- `message`
- `dashboard_state`

### `POST /update_day_metric`
Request JSON:
- metric-specific fields depending on the metric being updated

Response JSON:
- `message`
- `dashboard_state`

Purpose:
- generic updater for selected daily-entry metrics

### `POST /reset_day`
Response JSON:
- `message`
- `redirect_url`

Behavior:
- marks/clears current day state so onboarding can restart

### `POST /add_workout`
Request JSON:
- `activity_type`
- `duration`

Response JSON:
- `message`
- `dashboard_state`

### `POST /toggle_day_task`
### `POST /toggle_task_status`
Aliases to same function.

Request JSON:
- task identity payload, typically task `id`

Behavior:
- toggles completion for current user
- updates streaks and completion history
- syncs `daily_entries.completed_tasks_json`

Response JSON:
- `message`
- `dashboard_state`

### `POST /submit_energy`
Request JSON:
- answers array / score inputs for six questions

Response JSON:
- `message`
- `energy_percent`
- `dashboard_state`

### `POST /submit_day_data`
Request JSON:
- `tasks: string[]`
- `sleep_hours: number`
- `mood: Focused|Neutral|Stressed|Low Energy`
- `exercised: bool|string|number` convertible via parser

Response JSON:
- `plan`
- `redirect_url`

### `POST /analyze_health`
Request JSON:
- `height_cm`
- `weight_kg`

Response JSON:
- `message`
- `health`
- `dashboard_state`

### `POST /chat`
Request JSON:
- `message`

Response JSON:
- `response`
- `reply`
- `messages`
- `dashboard_state`
- `tool_used`
- `pending_task`

### `POST /chat/confirm_task`
Response JSON:
- `message`
- `reply`
- `dashboard_state`
- `pending_task: null`

### `POST /chat/cancel_task`
Response JSON:
- `message`
- `reply`
- `pending_task: null`

### `POST /ai-action`
Request JSON:
- `message`

Response JSON:
- `reply`

## External API Documentation

### Groq OpenAI-Compatible Chat API
Client construction:
- SDK class: `OpenAI`
- `api_key`: `GROQ_API_KEY`
- `base_url`: `https://api.groq.com/openai/v1`

Request structure:
- `model`
- `messages`
- optionally `tools`
- optionally `tool_choice`

Authentication method:
- API key in Authorization header handled by SDK.

---

## 8. AI Integration Documentation

### How AI Is Used
AI is used in two main modes:
1. conversational chat assistant (`/chat`)
2. one-shot contextual quick action (`/ai-action`)

### Prompt Engineering Strategy
There are multiple system-prompt layers.

Primary chat system prompt in `SYSTEM_PROMPT` and `get_openai_reply()` emphasizes:
- professional personal AI assistant behavior
- productivity and planning support
- concise, practical, structured suggestions
- contextual reasoning using real dashboard data
- explicit guardrail against silently creating tasks without user intent

Secondary prompt behavior:
- dashboard context is passed as a separate system message
- prior chat history is appended in role order
- current user message is appended last

### Task-Creation Tooling Strategy
The AI is allowed to create tasks only when `has_explicit_task_creation_intent(user_message)` returns true.

When explicit intent exists:
- `tools` array includes one function schema: `add_user_task`
- parameters:
  - `task_name`
  - `priority`
- tool choice is `auto`

Important architecture decision:
- The model is not always given tool permissions.
- Tool access is conditional and designed to prevent over-eager task insertion.

### AI Workflows

#### Workflow A: General advice
1. Collect dashboard context.
2. Send system prompt + dashboard context + chat history + user message.
3. Return plain model response.

#### Workflow B: Explicit task creation intent
1. Detect explicit task request.
2. Enable function-tool schema.
3. Model can return tool call.
4. Backend parses JSON tool arguments.
5. Backend inserts task using local business logic.
6. Backend returns success text and updated dashboard state.

#### Workflow C: Quick action
1. Frontend selects predefined prompt or user-entered message.
2. Backend sends stricter concise-response prompt with dashboard context.
3. Return reply text only.

### Memory Systems
There is no long-term LLM memory store.

Current memory architecture:
- in-memory chat history dictionary `CHAT_SESSIONS`
- in-memory pending-task dictionary `PENDING_AI_TASKS`
- history limited to `MAX_CHAT_MESSAGES = 20`
- session keyed by username + generated chat session id

Implications:
- memory is ephemeral across process restarts
- no memory sharing across multiple workers
- no semantic retrieval or vector DB
- no user profile persistence specifically for AI beyond operational data already in SQLite

### Recommendation Systems
Recommendations are rule-based, not ML-based.

Primary recommendation engine:
- `generate_daily_plan(data)`
- `build_dashboard_state(today_entry)`

Input factors include:
- sleep hours
- energy percent
- pending/completed tasks
- study hours
- exercise minutes
- calories burned
- current time of day
- health status
- career pipeline next action
- remaining study hours
- subjects not yet studied today

Output:
- a set of dynamic suggestions shown on dashboard

### Chatbot Architecture
Client side:
- embedded chat panel in `templates/index.html`
- controlled by `dashboard.js`
- supports quick prompt buttons and free text submission

Server side:
- `/chat` route
- `get_chat_history()` for session-scoped memory
- `get_openai_reply()` for orchestration
- `add_user_task_from_ai()` for trusted task insertion

Failure handling:
- AI unavailable -> safe fallback messages
- missing API key -> clear configuration error or fallback route behavior

---

## 9. User Interface Documentation

### UI Model
The UI is mobile-first and highly card-based. Styling aims for a modern personal assistant dashboard with gradient ambience, rounded panels, and embedded assistant surfaces.

### Pages

#### Login Page
File: `templates/login.html`
Elements:
- email field
- password field
- submit button
- link to registration

#### Registration Page
File: `templates/register.html`
Elements:
- username field
- email field
- password field
- submit button

#### Onboarding Page
File: `templates/onboarding.html`
Elements:
- task input and task list
- sleep input
- mood choice group
- exercise choice group
- workout-type picker visible conditionally
- suggestion cards
- skip intro preference
- submit/start day action

Navigation outcome:
- successful submit redirects to dashboard

#### Dashboard Page
File: `templates/index.html`
Sections include:
- welcome hero
- support panel
- AI guidance carousel
- streak panel
- skill suggestion panel
- embedded AI assistant chat shell
- progress/metric cards
- activity page section
- quick task form
- daily task list
- long-term goal list
- workout form/picker/list
- energy modal
- health form and insight area
- bottom navigation

#### Career Page
File: `templates/career.html`
Sections include:
- pipeline tracker
- skill focus toggles/progress
- study tracker
- subject chip manager
- AI quick prep buttons
- bottom navigation

#### Financial Page
File: `templates/financial.html`
Sections include:
- financial overview
- AI insight highlight
- instruments tracker
- quick expense logger
- monthly summary
- bottom navigation

### Components

#### Bottom Navigation
Shared partial.
Allows page switching between core sections.

#### Chat Widget
Located in dashboard page.
Contains:
- title/header
- close button
- quick prompt buttons
- message list
- input form

#### Task Panels
- daily tasks panel
- long-term goals panel
- quick add task form

#### Workout Panel
- wheel/click keyboard-driven workout picker
- duration input
- submit button
- workout history list

#### Health Panel
- height input
- weight input
- analyze button
- results container

### Navigation Flow
1. Unauthenticated user:
   - `/login` or `/register`
2. Authenticated user without daily setup:
   - `/` -> onboarding
3. Authenticated user with daily setup:
   - `/` -> `/dashboard`
4. Bottom nav moves to:
   - dashboard
   - career
   - financial
5. Dashboard internal tabs/sections support SPA-like switching.

### Dashboard Elements
The dashboard is composed from `dashboard_state`.
Likely major state-driven sections:
- metrics cards
- suggestions list/slides
- streak indicator
- tasks progress bar and metadata
- workout totals
- study stats
- health summary
- AI assistant state

---

## 10. Business Logic

### Productivity Calculations
Primary productivity logic is rule-based and derived from metrics.

Key calculated dimensions:
- task completion ratio
- sleep adequacy ratio against goal (8h)
- study progress ratio against target
- exercise ratio against 30 min goal
- calorie-burn ratio against 400 kcal reference
- energy percentage from questionnaire

These feed into dashboard suggestions and visual progress panels.

### Habit Calculations
Current habit model is simple:
- each streak update increments `streak` by 1
- no date validation or anti-double-counting guard in current implementation

This is not a robust habit engine; it is a manual streak counter.

### Study Calculations
There are two primary study calculations:
1. daily dashboard study progress:
   - `study_hours_total / study_goal`
2. career study progress:
   - today hours, weekly total, target hours, and subject coverage

`build_dashboard_state()` uses career study snapshot as the main study source for dashboard suggestion generation.

### Recommendation Logic
Recommendation logic is deterministic, contextual, and compositional.

Influencing inputs:
- sleep deficit or surplus
- current energy level
- pending tasks
- completed tasks
- workout completion
- calories burned
- health category and weight guidance
- career pipeline next action
- remaining study hours
- subjects not studied today
- current hour of day

This creates suggestions such as:
- when to prioritize recovery
- when to do focused study
- when to handle career pipeline actions
- when to begin with small wins vs hard tasks

### Health Calculations
`calculate_health_insight(height_cm, weight_kg)`:
- height in meters = `height_cm / 100`
- BMI = `weight_kg / (height_m ** 2)`
- ideal range derived using BMI thresholds 18.5 and 24.9

Additional guidance derived from:
- BMI category mapping
- estimated calorie adjustment by weight gap

### Workout Calculations
Calories burned = `duration * WORKOUT_CALORIE_RATES[activity_type]`

Exercise minutes total = sum of today’s workout durations.

### Task Streak Calculations
Completion history is stored per task in `completion_history_json`.
`compute_streak_from_history(values)` is used to derive streaks based on normalized date history.

This is more advanced than the habit streak feature and suggests the task system received more recent development attention.

---

## 11. Deployment Documentation

### Environment Variables
Observed and supported variables:
- `GROQ_API_KEY`
  - required for live AI responses
- `GROQ_MODEL`
  - optional override for default LLM model
- `PERSONAL_AI_OS_DB`
  - optional custom DB file path
- `PERSONAL_AI_OS_TIMEZONE`
  - timezone, default `Asia/Kolkata`
- `FLASK_SECRET_KEY`
  - preferred Flask secret
- `SECRET_KEY`
  - fallback Flask secret key source
- `FLASK_ENV`
  - influences production detection
- `RENDER`
  - production-host indicator used in cookie security logic
- `PORT`
  - runtime port

### Setup Instructions
1. Install Python 3.
2. Create virtual environment.
3. Activate environment.
4. Run `python -m pip install -r requirements.txt`.
5. Create `.env` with at least:
   - `GROQ_API_KEY=...`
   - `FLASK_SECRET_KEY=...`
6. Start app with `python app.py`.

### Local Development Instructions
- The app auto-installs core runtime deps at startup if missing.
- SQLite DB file is created or migrated automatically on launch.
- Debug server starts on `0.0.0.0` and default port `5000`.
- Startup creates expected directories if missing.

### Production Deployment Process
Current repository hints at deployment on Render and use of Gunicorn.

Likely production process:
1. Provision Python web service.
2. Install `requirements.txt`.
3. Set env vars:
   - `GROQ_API_KEY`
   - `FLASK_SECRET_KEY`
   - `PORT`
   - optionally DB path/timezone/model
4. Run Gunicorn against `app:app`.

Operational notes:
- `SESSION_COOKIE_SECURE` is enabled in production detection.
- SQLite in production is workable only for low-scale/single-instance usage.
- In-memory AI chat session state is not multi-instance safe.

### Architecture Decisions Affecting Deployment
- Monolith simplifies deployment: single process, no worker coordination required for core app logic.
- SQLite reduces infra complexity but limits concurrency/scalability.
- In-memory AI memory means sticky sessions or single-instance deployment are preferable.

---

## 12. Security Considerations

### Authentication
- Uses Flask-Login session-cookie authentication.
- Passwords are hashed, not stored in plaintext.
- Registration enforces uniqueness on username and email.

### API Key Handling
- AI key loaded from `.env` using `python-dotenv`.
- Current repository contains a real-looking `GROQ_API_KEY` in `.env`, which is a serious secret-management issue.
- Secrets should be rotated immediately and removed from version control.

### Session Security
Configured cookie protections:
- `SESSION_COOKIE_HTTPONLY=True`
- `SESSION_COOKIE_SAMESITE='Lax'`
- `SESSION_COOKIE_SECURE=IS_PRODUCTION`
- equivalent remember-cookie protections

### Data Protection
- SQLite stores user data locally.
- No explicit encryption at rest.
- No column-level encryption for health or personal productivity data.

### Missing Security Layers
- No CSRF protection visible for forms or JSON endpoints.
- No rate limiting.
- No account lockout or brute-force protection.
- No input sanitization framework beyond basic validation and Jinja escaping.
- No authorization layer beyond current-user ownership checks.
- No audit logging for sensitive actions.

### AI Security Considerations
- Dashboard context is directly injected into system messages.
- There is basic guardrail logic around task creation intent.
- There is no advanced prompt-injection mitigation or output filtering.
- AI cannot directly execute arbitrary tools; only one narrowly scoped task-add tool exists.

---

## 13. Known Issues

### Current Bugs / Risks
1. `.env` contains a sensitive API key in the repository.
2. `app.py` is very large and monolithic, which raises change risk and regression likelihood.
3. Study tracking exists in multiple overlapping systems (`study`, `daily_entries.study_hours_total`, `career_study_tracker`).
4. Daily tasks are duplicated between `daily_entries.tasks_json` and `tasks`, creating sync complexity.
5. Habit tracking appears less mature and may depend on schema migration having added `user` column.
6. In-memory chat state is lost on restart and unsafe for multi-worker scaling.
7. Financial feature is mostly mock/prototype and lacks backend persistence.
8. The application mixes `user` string references and `user_id` numeric references inconsistently.
9. No formal migration framework; schema drift is managed manually at runtime.
10. Some text encoding/artifact issues are visible in template/source output, suggesting encoding inconsistencies.

### Technical Debt
- Single-file backend.
- Mixed data modeling patterns.
- Limited testability due to tight coupling of routes and business logic.
- No test suite present.
- No package structure (`services`, `models`, `repositories`, etc.).
- No API schema/versioning.
- Frontend logic is large and imperative, especially `dashboard.js`.

### Limitations
- SQLite limits write concurrency and scale.
- No background jobs or async task processing.
- No real-time updates.
- No mobile app/native packaging.
- No persistent AI memory.
- No financial data backend.
- No admin tools or multi-tenant controls.

---

## 14. Future Roadmap

### Planned or Logical Next Features
1. Refactor backend into modules:
   - auth
   - dashboard
   - tasks
   - study
   - career
   - ai
   - db/models
2. Replace SQLite with PostgreSQL for production readiness.
3. Add proper migrations with Alembic.
4. Add test coverage for route handlers and calculation helpers.
5. Convert financial prototype into real persisted feature set.
6. Add richer habit engine with date-aware completions.
7. Add export/reporting features.
8. Add recurring tasks and reminders.
9. Add history views for trends across days/weeks/months.

### Scalability Improvements
- Move chat memory from process RAM to Redis or DB.
- Normalize task/day relationship instead of storing duplicated JSON.
- Introduce service layer and repository layer.
- Use PostgreSQL with indexed date/user columns.
- Split dashboard state assembly into composable services.
- Cache derived dashboard state if performance becomes an issue.

### AI Enhancements
- Persistent memory tied to user profile and prior activity summaries.
- Retrieval-augmented recommendations based on historical habits/study/workout patterns.
- Safer structured output schemas for all AI endpoints.
- Multi-step planner tools beyond task creation.
- AI-generated weekly reviews and health/study summaries.
- Career-focused mock interview stateful mode.

---

## 15. Developer Handover Summary

### What a New Developer Must Understand First
1. `app.py` contains nearly the entire backend. Read it end-to-end before making structural changes.
2. `daily_entries` is the center of the product model.
3. `build_dashboard_state()` is the most important state-aggregation function.
4. Daily tasks are mirrored in both JSON and normalized table form.
5. Career features are separate but feed the dashboard recommendation engine.
6. AI is integrated server-side only and uses Groq through OpenAI-compatible client semantics.

### Recommended Reading Order
1. `README.md`
2. `requirements.txt`
3. startup/config section of `app.py`
4. `init_db()` and database helpers in `app.py`
5. `get_today_entry()` and related daily access helpers
6. `build_dashboard_state()`
7. `get_openai_reply()`
8. route handlers from onboarding to dashboard to AI
9. `templates/index.html`
10. `static/js/dashboard.js`
11. career templates/scripts
12. onboarding template/script

### Safest Refactor Sequence
1. Extract configuration and app factory.
2. Extract DB helpers.
3. Extract auth helpers and routes.
4. Extract dashboard/business logic service layer.
5. Extract AI integration.
6. Add tests around behavior before data-model rewrites.
7. Only then normalize schema and remove duplicated task storage.

### Key Maintenance Hotspots
- `sync_today_task_records()`
- `toggle_day_task()`
- `build_dashboard_state()`
- `generate_daily_plan()`
- `get_openai_reply()`
- `init_db()` / `ensure_daily_entries_schema()`

### Development Priorities if Continuing This Project
1. Remove secrets from repo and rotate keys.
2. Add tests.
3. Break `app.py` into modules.
4. Unify study tracking model.
5. Normalize task/day data model.
6. Decide whether financial feature is real scope or prototype-only.

---

## 16. AI Handover Summary

### Project Identity
This is a Flask monolith named Personal AI OS. It is a personal productivity dashboard with day onboarding, tasks, study, workouts, health insights, career tracking, and AI assistant features.

### Core Conceptual Model
The project revolves around a single daily operating record per user in `daily_entries`. Most dashboard behavior depends on that row plus supporting tables (`tasks`, `workouts`, `career_*`, `health_data`, `energy_logs`).

### Primary Backend Control Points
- Flask app entry: `app.py`
- DB init/migration: `init_db()`
- daily state fetch: `get_today_entry()`
- dashboard aggregator: `build_dashboard_state()`
- AI orchestration: `get_openai_reply()`
- chat endpoint: `/chat`

### State Model You Must Preserve
If continuing development, preserve these invariants unless intentionally redesigning:
1. One daily entry per user/date.
2. Dashboard UI expects a rich `dashboard_state` JSON structure.
3. Daily tasks must remain consistent between dashboard and DB row views.
4. AI task creation should stay gated behind explicit user intent.
5. Career study data influences dashboard suggestions.

### Frontend Mental Model
- Dashboard is server-rendered but behaves like a client-side app after load.
- `dashboard.js` is the central frontend orchestrator.
- Career and onboarding have separate controllers.
- Financial page is mostly static/demo logic.

### Database Mental Model
- SQLite, weakly normalized.
- Uses username-string ownership for most tables.
- Uses integer `user_id` for some health/energy records.
- Several JSON arrays are stored in TEXT fields.
- Runtime migration logic mutates schema opportunistically.

### AI Mental Model
- AI is not the source of truth.
- AI is an assistant layered on top of deterministic app state.
- Prompting includes dashboard context as structured prose/system content.
- Tool usage is limited to task creation and only when explicit intent is detected.
- No long-term persistent LLM memory exists.

### If You Continue Development as Another AI
Recommended first tasks:
1. Read `app.py` fully.
2. Inspect `build_dashboard_state()` output shape.
3. Trace all fetch calls from `static/js/dashboard.js` to matching Flask routes.
4. Review `init_db()` and current live DB schema before changing tables.
5. Preserve existing response shapes unless simultaneously updating frontend consumers.
6. Treat financial feature as prototype unless you implement backend persistence.
7. Prefer incremental refactor with behavior-preserving tests before major redesign.

### Most Important Design Decisions Currently in Place
- Monolithic single-file backend chosen for speed of iteration.
- SQLite chosen for simplicity.
- Server-rendered templates chosen over SPA framework.
- AI acts as contextual advisor, not autonomous agent.
- Dashboard recommendations are rule-based and deterministic.
- Career and productivity domains are connected through shared dashboard suggestion logic.

### Highest-Risk Areas for Regression
- Task synchronization between `daily_entries` and `tasks`
- Dashboard state shape consumed by `dashboard.js`
- AI chat behavior around pending task confirmation
- Daily reset behavior
- Study totals across overlapping study systems
- Schema migration assumptions in `init_db()`
