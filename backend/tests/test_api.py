def create_task(client, login, title="Prepare report", assigned_to="user-2"):
    login()
    return client.post(
        "/api/tasks",
        json={"title": title, "description": "Quarterly summary", "assigned_to": assigned_to},
        headers={"Origin": "http://localhost:3000"},
    )


def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}
    assert client.get("/api/health/database").status_code == 200


def test_protected_endpoint_requires_login(client):
    assert client.get("/api/tasks").status_code == 401


def test_create_and_assign_task(client, login, email_service):
    response = create_task(client, login)
    assert response.status_code == 201
    assert response.get_json()["task"]["assigned_to"] == "user-2"
    assert len(email_service.assignments) == 1


def test_email_failure_does_not_undo_task(client, login, email_service, database):
    def fail_email(_task, _frontend_url):
        raise RuntimeError("temporary Gmail failure")

    email_service.notify_assignment = fail_email
    response = create_task(client, login)
    assert response.status_code == 201
    assert response.get_json()["email_sent"] is False
    assert len(database.tasks) == 1


def test_rejects_invalid_task_data(client, login):
    assert create_task(client, login, title="   ").status_code == 400
    assert create_task(client, login, assigned_to="missing").status_code == 400


def test_retrieves_only_related_tasks(client, login):
    create_task(client, login)
    login("user-3")
    assert client.get("/api/tasks").get_json()["tasks"] == []
    login("user-2")
    assert len(client.get("/api/tasks?scope=assigned").get_json()["tasks"]) == 1


def test_assignee_can_complete_task(client, login, email_service):
    task_id = create_task(client, login).get_json()["task"]["id"]
    login("user-2")
    response = client.post(
        f"/api/tasks/{task_id}/complete",
        json={},
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.get_json()["task"]["status"] == "completed"
    assert len(email_service.completions) == 1


def test_unrelated_user_cannot_view_or_complete(client, login):
    task_id = create_task(client, login).get_json()["task"]["id"]
    login("user-3")
    assert client.get(f"/api/tasks/{task_id}").status_code == 403
    response = client.post(
        f"/api/tasks/{task_id}/complete",
        json={},
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 403


def test_completed_task_cannot_be_completed_twice(client, login):
    task_id = create_task(client, login).get_json()["task"]["id"]
    first = client.post(
        f"/api/tasks/{task_id}/complete", json={}, headers={"Origin": "http://localhost:3000"}
    )
    second = client.post(
        f"/api/tasks/{task_id}/complete", json={}, headers={"Origin": "http://localhost:3000"}
    )
    assert first.status_code == 200
    assert second.status_code == 409


def test_only_creator_can_edit(client, login):
    task_id = create_task(client, login).get_json()["task"]["id"]
    login("user-2")
    response = client.patch(
        f"/api/tasks/{task_id}",
        json={"title": "Changed"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 403


def test_creator_can_reassign_and_new_assignee_is_emailed(client, login, email_service):
    task_id = create_task(client, login).get_json()["task"]["id"]
    response = client.patch(
        f"/api/tasks/{task_id}",
        json={"assigned_to": "user-3"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.get_json()["task"]["assigned_to"] == "user-3"
    assert response.get_json()["email_sent"] is True
    assert len(email_service.assignments) == 2
