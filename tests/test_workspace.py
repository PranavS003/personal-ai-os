import importlib
import json
import os
import re
import secrets
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from werkzeug.security import generate_password_hash


class WorkspaceTestCase(unittest.TestCase):
    password = "workspace-test-password"
    due_date = "2099-04-08"

    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        cls.test_directory = Path(scratch.name)
        import_database = cls.test_directory / "app-import.db"
        environment = {
            "PERSONAL_AI_OS_DB": str(import_database),
            "FLASK_ENV": "development",
            "FLASK_SECRET_KEY": secrets.token_hex(32),
            "RENDER": "",
            "GROQ_API_KEY": "",
        }
        with patch.dict(os.environ, environment), patch("dotenv.load_dotenv"):
            cls.database = importlib.import_module("database.db")
            with patch.multiple(cls.database, DATABASE_FILE=import_database, DATABASE_PATH=str(import_database)):
                cls.app_module = importlib.import_module("app")
        cls.app = cls.app_module.app

    def setUp(self):
        database_path = self.test_directory / f"{self._testMethodName}.db"
        self.mock_database(database_path)
        self.start_patch(patch.dict(self.app.config, {"TESTING": True, "SESSION_COOKIE_SECURE": False}))
        self.start_patch(patch.object(self.app_module, "get_ai_client", side_effect=AssertionError("Unexpected AI call")))
        self.mail = self.start_patch(patch.object(self.app_module, "send_password_reset_email", autospec=True))
        self.database.init_db(self.app.logger)
        self.client = self.app.test_client()

    def start_patch(self, patcher):
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def mock_database(self, path):
        self.start_patch(patch.multiple(self.database, DATABASE_FILE=path, DATABASE_PATH=str(path)))

    def token(self, client, path="/workspace/tasks"):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        token = re.search(r'name="auth_form_token" value="([^"]+)"', response.get_data(as_text=True))
        self.assertIsNotNone(token, f"CSRF token missing from {path}")
        return token[1]

    def assert_redirect(self, response, path, status):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.headers["Location"], path)

    def register(self, client, username="alice"):
        response = client.post("/register", data={
            "username": username,
            "email": f"{username}@example.test",
            "password": self.password,
            "auth_form_token": self.token(client, "/register"),
        })
        self.assert_redirect(response, "/", 302)

    def login(self, client, username, password):
        return client.post("/login", data={
            "email": f"{username}@example.test",
            "password": password,
            "auth_form_token": self.token(client, "/login"),
        })

    def create_task(self, client, title, return_to="tasks"):
        path = "/dashboard" if return_to == "today" else "/workspace/tasks"
        response = client.post("/workspace/tasks", data={
            "title": title,
            "priority": "High",
            "due_date": self.due_date,
            "return_to": return_to,
            "auth_form_token": self.token(client, path),
        })
        self.assert_redirect(response, path, 303)
        return next(task for task in self.saved_tasks(client) if task["name"] == title)

    def saved_tasks(self, client):
        response = client.get("/tasks")
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def task_row(self, task_id):
        with closing(self.database.get_db_connection()) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()

    def task_action(self, client, task_id, action, **fields):
        return client.post(f"/workspace/tasks/{task_id}/{action}", data={
            "return_to": "tasks",
            "auth_form_token": self.token(client),
            **fields,
        })

    def test_today_and_tasks_are_usable_without_a_daily_entry(self):
        for path in ("/", "/dashboard", "/workspace/tasks"):
            with self.subTest(path=path):
                self.assert_redirect(self.client.get(path), "/login", 302)

        self.register(self.client)
        self.assert_redirect(self.client.get("/"), "/dashboard", 302)
        self.token(self.client, "/dashboard")
        self.token(self.client)
        self.assertEqual(self.saved_tasks(self.client), [])
        with closing(self.database.get_db_connection()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM daily_entries").fetchone()[0], 0)

        response = self.client.post("/workspace/tasks", data={
            "title": "Plan tomorrow", "priority": "Medium", "return_to": "today",
            "auth_form_token": self.token(self.client, "/dashboard"),
        })
        self.assert_redirect(response, "/dashboard", 303)
        task = self.saved_tasks(self.client)[0]
        self.assertIsNone(self.task_row(task["id"])["due_date"])
        self.assertIn(b"Plan tomorrow", self.client.get("/dashboard").data)

    def test_task_lifecycle_preserves_the_id_and_separates_due_date(self):
        self.register(self.client)
        created = self.create_task(self.client, "Review invoices", return_to="today")
        task_id = created["id"]
        original = self.task_row(task_id)
        self.assertEqual(original["due_date"], self.due_date)
        self.assertNotEqual(original["entry_date"], original["due_date"])

        self.assertEqual(self.client.get(f"/workspace/tasks/{task_id}/edit").status_code, 200)
        self.assert_redirect(self.task_action(
            self.client, task_id, "edit", title="File invoices", priority="Low", due_date="2099-04-11"
        ), "/workspace/tasks", 303)
        updated = self.task_row(task_id)
        self.assertEqual((updated["name"], updated["priority"], updated["due_date"]),
                         ("File invoices", "Low", "2099-04-11"))
        self.assertEqual(updated["entry_date"], original["entry_date"])
        self.assertEqual(self.saved_tasks(self.client)[0]["id"], task_id)

        for completed in (True, True, False):
            with self.subTest(completed=completed):
                self.assert_redirect(self.task_action(self.client, task_id, "status", completed=int(completed)),
                                     "/workspace/tasks", 303)
                self.assertIs(self.saved_tasks(self.client)[0]["completed"], completed)

        self.assert_redirect(self.task_action(self.client, task_id, "delete"), "/workspace/tasks", 303)
        self.assertEqual(self.saved_tasks(self.client), [])
        self.assertEqual(self.task_row(task_id)["is_cleared"], 1)
        self.assertEqual(self.client.get(f"/workspace/tasks/{task_id}/edit").status_code, 404)

    def test_task_validation_and_csrf_reject_writes(self):
        self.register(self.client)
        valid_fields = {"title": "Valid task", "priority": "Medium", "due_date": self.due_date, "return_to": "tasks"}
        self.assertEqual(self.client.post("/workspace/tasks", data=valid_fields).status_code, 400)
        for fields in ({"title": " "}, {"priority": "Urgent"}, {"due_date": "2099-02-30"}):
            with self.subTest(fields=fields):
                response = self.client.post("/workspace/tasks", data={
                    **valid_fields, **fields, "auth_form_token": self.token(self.client),
                })
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.saved_tasks(self.client), [])

        task_id = self.create_task(self.client, "Must remain open")["id"]
        for action, fields in (
            ("edit", {"title": "Changed", "priority": "Low"}),
            ("status", {"completed": 1}),
            ("delete", {}),
        ):
            with self.subTest(action=action):
                response = self.client.post(f"/workspace/tasks/{task_id}/{action}", data=fields)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.task_action(self.client, task_id, "status", completed="unknown").status_code, 400)
        saved = self.saved_tasks(self.client)[0]
        self.assertEqual(saved["name"], "Must remain open")
        self.assertFalse(saved["completed"])

    def test_accounts_cannot_see_or_modify_each_others_tasks(self):
        self.register(self.client)
        task_id = self.create_task(self.client, "Private reconciliation")["id"]
        other = self.app.test_client()
        self.register(other, "bob")

        self.assertNotIn(b"Private reconciliation", other.get("/workspace/tasks").data)
        self.assertEqual(self.saved_tasks(other), [])
        self.assertEqual(other.get(f"/workspace/tasks/{task_id}/edit").status_code, 404)
        for action, fields in (
            ("edit", {"title": "Changed", "priority": "Low", "due_date": self.due_date}),
            ("status", {"completed": 1}),
            ("delete", {}),
        ):
            with self.subTest(action=action):
                self.assertEqual(self.task_action(other, task_id, action, **fields).status_code, 404)
        saved = self.saved_tasks(self.client)[0]
        self.assertEqual(saved["name"], "Private reconciliation")
        self.assertFalse(saved["completed"])

    def test_legacy_day_setup_keeps_existing_workspace_tasks(self):
        self.register(self.client)
        task_id = self.create_task(self.client, "Reserve a room")["id"]
        self.assert_redirect(self.task_action(self.client, task_id, "status", completed=1), "/workspace/tasks", 303)

        day_setup = {"tasks": ["Send the agenda"], "sleep_hours": 7, "mood": "Neutral", "exercised": False}
        for _ in range(2):
            response = self.client.post("/submit_day_data", json=day_setup)
            self.assertEqual(response.status_code, 200)
        saved_tasks = self.saved_tasks(self.client)
        self.assertCountEqual([task["name"] for task in saved_tasks], ["Reserve a room", "Send the agenda"])
        room = next(task for task in saved_tasks if task["name"] == "Reserve a room")
        self.assertEqual(room["id"], task_id)
        self.assertTrue(room["completed"])
        self.assertEqual(self.task_row(task_id)["due_date"], self.due_date)
        legacy_dashboard = self.client.get("/dashboard?legacy=1")
        self.assertEqual(legacy_dashboard.status_code, 200)
        self.assertIn(b"Reserve a room", legacy_dashboard.data)
        self.assertIn(b"Send the agenda", legacy_dashboard.data)

    def test_legacy_goal_api_uses_saved_tasks_without_daily_setup(self):
        self.register(self.client)
        response = self.client.post("/add_task", json={
            "task": "Practice piano", "priority": "Medium", "type": "long_term",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["dashboard_state"])
        task_id = self.saved_tasks(self.client)[0]["id"]

        for _ in range(2):
            response = self.client.post("/toggle_task_status", json={
                "task_id": task_id, "type": "long_term", "completed": True,
            })
            self.assertEqual(response.status_code, 200)
        saved = self.saved_tasks(self.client)[0]
        self.assertEqual(saved["type"], "long_term")
        self.assertEqual(saved["streak_count"], 1)
        self.assertEqual(len(json.loads(self.task_row(task_id)["completion_history_json"])), 1)

    def test_existing_long_task_titles_can_keep_their_text_when_edited(self):
        self.register(self.client)
        task_id = self.create_task(self.client, "Legacy task")["id"]
        legacy_title = "Existing title " * 20 + "end"
        with closing(self.database.get_db_connection()) as connection, connection:
            connection.execute("UPDATE tasks SET name = ? WHERE id = ?", (legacy_title, task_id))

        self.assert_redirect(self.task_action(
            self.client, task_id, "edit", title=legacy_title, priority="Low", due_date="",
        ), "/workspace/tasks", 303)
        edited = self.task_row(task_id)
        self.assertEqual(edited["name"], legacy_title)
        self.assertEqual(edited["priority"], "Low")
        self.assertIsNone(edited["due_date"])
        self.assertEqual(self.client.get(f"/workspace/tasks/{2**63}/edit").status_code, 404)

    def test_legacy_reset_reopens_setup_and_preserves_tasks_and_workouts(self):
        self.register(self.client)
        day_setup = {"tasks": ["Send the agenda"], "sleep_hours": 7, "mood": "Neutral", "exercised": False}
        self.assertEqual(self.client.post("/submit_day_data", json=day_setup).status_code, 200)
        task_id = self.create_task(self.client, "Reserve a room")["id"]
        workout = self.client.post("/add_workout", json={"activity_type": "Walking", "duration": 18})
        self.assertEqual(workout.status_code, 200)

        reset = self.client.post("/reset_day")
        self.assertEqual(reset.status_code, 200)
        setup_path = reset.get_json()["redirect_url"]
        self.assertEqual(urlsplit(setup_path).path, "/daily-setup")
        setup = self.client.get(setup_path)
        self.assertEqual(setup.status_code, 200)
        self.assertIn(b'dailySetupForm', setup.data)

        self.assertIn(task_id, {task["id"] for task in self.saved_tasks(self.client)})
        self.assertEqual(self.task_row(task_id)["due_date"], self.due_date)
        with closing(self.database.get_db_connection()) as connection:
            workouts = connection.execute("SELECT activity_type, duration, is_cleared FROM workouts").fetchall()
        self.assertEqual(workouts, [("Walking", 18, 0)])

    def test_legacy_json_task_backfill_preserves_existing_and_cleared_rows(self):
        path = self.test_directory / "legacy-fixture.db"
        self.mock_database(path)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.executescript("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE daily_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT NOT NULL, entry_date TEXT NOT NULL,
                    tasks_json TEXT NOT NULL, completed_tasks_json TEXT NOT NULL DEFAULT '[]',
                    sleep_hours REAL NOT NULL, mood TEXT NOT NULL, energy_level INTEGER NOT NULL DEFAULT 0,
                    exercised INTEGER NOT NULL, plan TEXT NOT NULL, is_cleared INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, UNIQUE(user, entry_date)
                );
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, user TEXT NOT NULL DEFAULT '',
                    entry_date TEXT NOT NULL DEFAULT '', priority TEXT NOT NULL DEFAULT 'Medium',
                    task_type TEXT NOT NULL DEFAULT 'daily', completed INTEGER NOT NULL DEFAULT 0,
                    is_cleared INTEGER NOT NULL DEFAULT 0
                );
                INSERT INTO tasks (id, user, entry_date, name, priority, completed, is_cleared) VALUES
                    (100, 'legacy', '2023-04-01', 'Paper draft', 'High', 1, 0),
                    (101, 'legacy', '2023-04-01', 'Previously cleared', 'Low', 0, 1);
            """)
            connection.execute("INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                               ("legacy", "legacy@example.test", generate_password_hash(self.password), "2023-04-01"))
            connection.executemany("""
                INSERT INTO daily_entries (user, entry_date, tasks_json, completed_tasks_json,
                                           sleep_hours, mood, exercised, plan, is_cleared, created_at)
                VALUES ('legacy', ?, ?, ?, 7, 'Neutral', 0, '', ?, '2023-04-01')
            """, (
                ("2023-04-01", json.dumps(["Paper draft", "Review notes", "Previously cleared"]), '["Review notes"]', 0),
                ("2023-04-02", '["Cleared day"]', "[]", 1),
            ))

        self.database.init_db(self.app.logger)
        self.assert_redirect(self.login(self.client, "legacy", self.password), "/", 302)
        tasks = {task["name"]: task for task in self.saved_tasks(self.client)}
        self.assertEqual(set(tasks), {"Paper draft", "Review notes"})
        self.assertEqual(tasks["Paper draft"]["id"], 100)
        self.assertEqual(tasks["Paper draft"]["priority"], "High")
        self.assertTrue(tasks["Paper draft"]["completed"])
        self.assertTrue(tasks["Review notes"]["completed"])
        self.assertEqual(tasks["Review notes"]["entry_date"], "2023-04-01")

        self.database.init_db(self.app.logger)
        self.assertCountEqual(self.saved_tasks(self.client), list(tasks.values()))
        self.assertEqual(self.task_row(101)["is_cleared"], 1)
        with closing(self.database.get_db_connection()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM daily_entries").fetchone()[0], 2)

    def test_password_reset_and_logout_keep_working(self):
        self.register(self.client)
        reset_client = self.app.test_client()
        credentials = {
            "RESEND_API_KEY": "resend-test-key",
            "PASSWORD_RESET_FROM": "reset@example.test",
            "APP_BASE_URL": "https://workspace.example.test",
        }
        with patch.dict(os.environ, credentials):
            requested = reset_client.post("/forgot-password", data={
                "email": "alice@example.test",
                "auth_form_token": self.token(reset_client, "/forgot-password"),
            })
        self.assert_redirect(requested, "/forgot-password", 302)
        self.mail.assert_called_once()
        email, recovery_link = self.mail.call_args.args
        self.assertEqual(email, "alice@example.test")
        recovery_path = urlsplit(recovery_link).path

        new_password = "another-workspace-test-password"
        reset = reset_client.post(recovery_path, data={
            "password": new_password,
            "confirm_password": new_password,
            "auth_form_token": self.token(reset_client, recovery_path),
        })
        self.assert_redirect(reset, "/login", 302)
        self.assertEqual(reset_client.get(recovery_path).status_code, 400)
        self.assert_redirect(self.client.get("/dashboard"), "/login", 302)
        self.assertEqual(self.login(reset_client, "alice", self.password).status_code, 200)
        self.assert_redirect(self.login(reset_client, "alice", new_password), "/", 302)

        response = reset_client.post("/logout", data={"auth_form_token": self.token(reset_client, "/dashboard")})
        self.assert_redirect(response, "/login", 302)
        self.assert_redirect(reset_client.get("/workspace/tasks"), "/login", 302)


if __name__ == "__main__":
    unittest.main()
