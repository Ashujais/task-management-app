from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


TASK_SELECT = """
SELECT t.id, t.title, t.description, t.status, t.created_at, t.updated_at,
       t.completed_at, t.created_by, t.assigned_to,
       creator.name AS creator_name, creator.email AS creator_email,
       assignee.name AS assignee_name, assignee.email AS assignee_email
FROM tasks t
JOIN users creator ON creator.id = t.created_by
JOIN users assignee ON assignee.id = t.assigned_to
"""


class Database:
    def __init__(self, database_url):
        self.database_url = database_url

    @contextmanager
    def connect(self):
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection

    def healthcheck(self):
        with self.connect() as connection:
            connection.execute("SELECT 1")

    def upsert_user(self, profile):
        with self.connect() as connection:
            return connection.execute(
                """
                INSERT INTO users (google_id, name, email, avatar_url)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (google_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    email = EXCLUDED.email,
                    avatar_url = EXCLUDED.avatar_url,
                    updated_at = NOW()
                RETURNING id, google_id, name, email, avatar_url, created_at, updated_at
                """,
                (profile["sub"], profile["name"], profile["email"].lower(), profile.get("picture")),
            ).fetchone()

    def list_users(self):
        with self.connect() as connection:
            return connection.execute(
                "SELECT id, name, email, avatar_url FROM users ORDER BY name, email"
            ).fetchall()

    def get_user(self, user_id):
        with self.connect() as connection:
            return connection.execute(
                "SELECT id, name, email, avatar_url FROM users WHERE id = %s", (user_id,)
            ).fetchone()

    def create_task(self, title, description, created_by, assigned_to):
        with self.connect() as connection:
            exists = connection.execute("SELECT 1 FROM users WHERE id = %s", (assigned_to,)).fetchone()
            if not exists:
                return None
            row = connection.execute(
                """
                INSERT INTO tasks (title, description, created_by, assigned_to)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (title, description, created_by, assigned_to),
            ).fetchone()
            return connection.execute(TASK_SELECT + " WHERE t.id = %s", (row["id"],)).fetchone()

    def list_tasks(self, user_id, scope=None, status=None):
        conditions = ["(t.created_by = %s OR t.assigned_to = %s)"]
        params = [user_id, user_id]
        if scope == "created":
            conditions = ["t.created_by = %s"]
            params = [user_id]
        elif scope == "assigned":
            conditions = ["t.assigned_to = %s"]
            params = [user_id]
        if status:
            conditions.append("t.status = %s")
            params.append(status)
        query = TASK_SELECT + " WHERE " + " AND ".join(conditions) + " ORDER BY t.created_at DESC"
        with self.connect() as connection:
            return connection.execute(query, params).fetchall()

    def get_task(self, task_id):
        with self.connect() as connection:
            return connection.execute(TASK_SELECT + " WHERE t.id = %s", (task_id,)).fetchone()

    def update_task(self, task_id, user_id, title, description, assigned_to):
        with self.connect() as connection:
            exists = connection.execute("SELECT 1 FROM users WHERE id = %s", (assigned_to,)).fetchone()
            if not exists:
                return None
            updated = connection.execute(
                """
                UPDATE tasks SET title = %s, description = %s, assigned_to = %s, updated_at = NOW()
                WHERE id = %s AND created_by = %s AND status = 'pending'
                RETURNING id
                """,
                (title, description, assigned_to, task_id, user_id),
            ).fetchone()
            if not updated:
                return False
            return connection.execute(TASK_SELECT + " WHERE t.id = %s", (task_id,)).fetchone()

    def complete_task(self, task_id, user_id):
        with self.connect() as connection:
            updated = connection.execute(
                """
                UPDATE tasks SET status = 'completed', completed_at = NOW(), updated_at = NOW()
                WHERE id = %s AND (assigned_to = %s OR created_by = %s) AND status = 'pending'
                RETURNING id
                """,
                (task_id, user_id, user_id),
            ).fetchone()
            if not updated:
                return None
            return connection.execute(TASK_SELECT + " WHERE t.id = %s", (task_id,)).fetchone()

