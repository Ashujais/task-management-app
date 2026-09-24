from functools import wraps

from flask import Blueprint, current_app, jsonify, redirect, request, session, url_for

from .email_service import send_safely

api = Blueprint("api", __name__, url_prefix="/api")


def db():
    return current_app.extensions["database"]


def current_user():
    user_id = session.get("user_id")
    return db().get_user(user_id) if user_id else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            session.clear()
            return jsonify({"error": "Authentication required"}), 401
        return view(user, *args, **kwargs)

    return wrapped


def serialize(value):
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value) if value.__class__.__name__ == "UUID" else value


@api.get("/health")
def health():
    return jsonify({"status": "ok"})


@api.get("/health/database")
def database_health():
    try:
        db().healthcheck()
        return jsonify({"status": "ok", "database": "connected"})
    except Exception:
        current_app.logger.exception("Database health check failed")
        return jsonify({"status": "unavailable", "database": "disconnected"}), 503


@api.get("/auth/google")
def google_login():
    redirect_uri = current_app.config["GOOGLE_REDIRECT_URI"] or url_for(
        "api.google_callback", _external=True
    )
    return current_app.extensions["google_oauth"].authorize_redirect(redirect_uri)


@api.get("/auth/google/callback")
def google_callback():
    try:
        token = current_app.extensions["google_oauth"].authorize_access_token()
        profile = token.get("userinfo")
        if not profile:
            profile = current_app.extensions["google_oauth"].userinfo(token=token)
        if not profile.get("email_verified", False):
            raise ValueError("Google email is not verified")
        user = db().upsert_user(profile)
        session.clear()
        session.permanent = True
        session["user_id"] = str(user["id"])
        return redirect(f"{current_app.config['FRONTEND_URL']}/dashboard")
    except Exception:
        current_app.logger.exception("Google OAuth callback failed")
        return redirect(f"{current_app.config['FRONTEND_URL']}/login?error=oauth_failed")


@api.post("/auth/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@api.get("/users/me")
@login_required
def me(user):
    return jsonify({"user": serialize(user)})


@api.get("/users")
@login_required
def users(_user):
    return jsonify({"users": serialize(db().list_users())})


@api.post("/tasks")
@login_required
def create_task(user):
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    assigned_to = str(data.get("assigned_to", "")).strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    if len(title) > 200:
        return jsonify({"error": "Title must be 200 characters or fewer"}), 400
    if len(description) > 5000:
        return jsonify({"error": "Description must be 5000 characters or fewer"}), 400
    if not assigned_to:
        return jsonify({"error": "Assigned user is required"}), 400
    task = db().create_task(title, description, str(user["id"]), assigned_to)
    if not task:
        return jsonify({"error": "Assigned user does not exist"}), 400
    email_sent = send_safely(
        lambda: current_app.extensions["email_service"].notify_assignment(
            task, current_app.config["FRONTEND_URL"]
        ),
        "task_assigned",
    )
    return jsonify({"task": serialize(task), "email_sent": email_sent}), 201


@api.get("/tasks")
@login_required
def list_tasks(user):
    scope = request.args.get("scope")
    status = request.args.get("status")
    if scope not in {None, "created", "assigned"}:
        return jsonify({"error": "scope must be created or assigned"}), 400
    if status not in {None, "pending", "completed"}:
        return jsonify({"error": "status must be pending or completed"}), 400
    tasks = db().list_tasks(str(user["id"]), scope, status)
    return jsonify({"tasks": serialize(tasks)})


@api.get("/tasks/<task_id>")
@login_required
def get_task(user, task_id):
    task = db().get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    if str(user["id"]) not in {str(task["created_by"]), str(task["assigned_to"])}:
        return jsonify({"error": "You cannot view this task"}), 403
    return jsonify({"task": serialize(task)})


@api.patch("/tasks/<task_id>")
@login_required
def update_task(user, task_id):
    existing = db().get_task(task_id)
    if not existing:
        return jsonify({"error": "Task not found"}), 404
    if str(existing["created_by"]) != str(user["id"]):
        return jsonify({"error": "Only the task creator can edit this task"}), 403
    if existing["status"] == "completed":
        return jsonify({"error": "Completed tasks cannot be edited"}), 409
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", existing["title"])).strip()
    description = str(data.get("description", existing["description"])).strip()
    assigned_to = str(data.get("assigned_to", existing["assigned_to"])).strip()
    if not title or len(title) > 200 or len(description) > 5000:
        return jsonify({"error": "Task data is invalid"}), 400
    task = db().update_task(task_id, str(user["id"]), title, description, assigned_to)
    if task is None:
        return jsonify({"error": "Assigned user does not exist"}), 400
    if task is False:
        return jsonify({"error": "Task could not be updated"}), 409
    email_sent = None
    if str(existing["assigned_to"]) != assigned_to:
        email_sent = send_safely(
            lambda: current_app.extensions["email_service"].notify_assignment(
                task, current_app.config["FRONTEND_URL"]
            ),
            "task_reassigned",
        )
    return jsonify({"task": serialize(task), "email_sent": email_sent})


@api.post("/tasks/<task_id>/complete")
@login_required
def complete_task(user, task_id):
    existing = db().get_task(task_id)
    if not existing:
        return jsonify({"error": "Task not found"}), 404
    if str(user["id"]) not in {str(existing["created_by"]), str(existing["assigned_to"])}:
        return jsonify({"error": "You cannot complete this task"}), 403
    if existing["status"] == "completed":
        return jsonify({"error": "Task is already completed"}), 409
    task = db().complete_task(task_id, str(user["id"]))
    if not task:
        return jsonify({"error": "Task could not be completed"}), 409
    email_sent = send_safely(
        lambda: current_app.extensions["email_service"].notify_completion(
            task, user, current_app.config["FRONTEND_URL"]
        ),
        "task_completed",
    )
    return jsonify({"task": serialize(task), "email_sent": email_sent})
