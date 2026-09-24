from datetime import datetime, timezone

import pytest

from app import create_app


class FakeDatabase:
    def __init__(self):
        self.users = {
            "user-1": {"id": "user-1", "name": "Asha", "email": "asha@example.com", "avatar_url": None},
            "user-2": {"id": "user-2", "name": "Ben", "email": "ben@example.com", "avatar_url": None},
            "user-3": {"id": "user-3", "name": "Cara", "email": "cara@example.com", "avatar_url": None},
        }
        self.tasks = {}
        self.now = datetime.now(timezone.utc)

    def healthcheck(self):
        return None

    def get_user(self, user_id):
        return self.users.get(user_id)

    def list_users(self):
        return list(self.users.values())

    def _expand(self, task):
        creator = self.users[task["created_by"]]
        assignee = self.users[task["assigned_to"]]
        return {
            **task,
            "creator_name": creator["name"],
            "creator_email": creator["email"],
            "assignee_name": assignee["name"],
            "assignee_email": assignee["email"],
        }

    def create_task(self, title, description, created_by, assigned_to):
        if assigned_to not in self.users:
            return None
        task_id = f"task-{len(self.tasks) + 1}"
        task = {
            "id": task_id,
            "title": title,
            "description": description,
            "created_by": created_by,
            "assigned_to": assigned_to,
            "status": "pending",
            "created_at": self.now,
            "updated_at": self.now,
            "completed_at": None,
        }
        self.tasks[task_id] = task
        return self._expand(task)

    def list_tasks(self, user_id, scope=None, status=None):
        values = list(self.tasks.values())
        if scope == "created":
            values = [task for task in values if task["created_by"] == user_id]
        elif scope == "assigned":
            values = [task for task in values if task["assigned_to"] == user_id]
        else:
            values = [task for task in values if user_id in {task["created_by"], task["assigned_to"]}]
        if status:
            values = [task for task in values if task["status"] == status]
        return [self._expand(task) for task in values]

    def get_task(self, task_id):
        task = self.tasks.get(task_id)
        return self._expand(task) if task else None

    def update_task(self, task_id, user_id, title, description, assigned_to):
        if assigned_to not in self.users:
            return None
        task = self.tasks[task_id]
        if task["created_by"] != user_id or task["status"] != "pending":
            return False
        task.update(title=title, description=description, assigned_to=assigned_to)
        return self._expand(task)

    def complete_task(self, task_id, user_id):
        task = self.tasks[task_id]
        if user_id not in {task["created_by"], task["assigned_to"]}:
            return None
        task.update(status="completed", completed_at=self.now, updated_at=self.now)
        return self._expand(task)


class FakeEmail:
    def __init__(self):
        self.assignments = []
        self.completions = []

    def notify_assignment(self, task, frontend_url):
        self.assignments.append((task, frontend_url))

    def notify_completion(self, task, user, frontend_url):
        self.completions.append((task, user, frontend_url))


@pytest.fixture
def database():
    return FakeDatabase()


@pytest.fixture
def email_service():
    return FakeEmail()


@pytest.fixture
def app(database, email_service):
    return create_app(
        {"TESTING": True, "SECRET_KEY": "test", "FRONTEND_URL": "http://localhost:3000"},
        database=database,
        email_service=email_service,
    )


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login(client):
    def do_login(user_id="user-1"):
        with client.session_transaction() as session:
            session["user_id"] = user_id

    return do_login

