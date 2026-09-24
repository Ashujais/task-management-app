"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Task, User } from "../../lib/api";

type Filter = "all" | "assigned" | "created" | "pending" | "completed";

export default function Dashboard() {
  const router = useRouter();
  const [me, setMe] = useState<User | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [completing, setCompleting] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assignedTo, setAssignedTo] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([
        api<{ user: User }>("/api/users/me"),
        api<{ users: User[] }>("/api/users"),
        api<{ tasks: Task[] }>("/api/tasks"),
      ])
      .then(([meData, usersData, tasksData]) => {
        if (cancelled) return;
      setMe(meData.user);
      setUsers(usersData.users);
      setTasks(tasksData.tasks);
      setAssignedTo((current) => current || usersData.users[0]?.id || "");
      })
      .catch((requestError: unknown) => {
        if (cancelled) return;
      if (requestError instanceof Error && requestError.message === "Authentication required") {
        router.replace("/login");
        return;
      }
      setError(requestError instanceof Error ? requestError.message : "Unable to load the dashboard.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  const filteredTasks = useMemo(() => {
    if (!me) return [];
    if (filter === "assigned") return tasks.filter((task) => task.assigned_to === me.id);
    if (filter === "created") return tasks.filter((task) => task.created_by === me.id);
    if (filter === "pending" || filter === "completed") {
      return tasks.filter((task) => task.status === filter);
    }
    return tasks;
  }, [filter, me, tasks]);

  async function createTask(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    if (!title.trim() || !assignedTo) {
      setError("Add a title and choose an assignee.");
      return;
    }
    setSaving(true);
    try {
      const result = await api<{ task: Task; email_sent: boolean }>("/api/tasks", {
        method: "POST",
        body: JSON.stringify({ title, description, assigned_to: assignedTo }),
      });
      setTasks((current) => [result.task, ...current]);
      setTitle("");
      setDescription("");
      setShowForm(false);
      setNotice(
        result.email_sent
          ? "Task created and the assignee was emailed."
          : "Task created. The email could not be sent; the task is safely saved."
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to create the task.");
    } finally {
      setSaving(false);
    }
  }

  async function completeTask(taskId: string) {
    setError("");
    setNotice("");
    setCompleting(taskId);
    try {
      const result = await api<{ task: Task; email_sent: boolean }>(
        `/api/tasks/${taskId}/complete`,
        { method: "POST", body: "{}" }
      );
      setTasks((current) => current.map((task) => (task.id === taskId ? result.task : task)));
      setNotice(
        result.email_sent
          ? "Task completed and the creator was emailed."
          : "Task completed. The email could not be sent; the update is safely saved."
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to complete the task.");
    } finally {
      setCompleting(null);
    }
  }

  async function logout() {
    await api("/api/auth/logout", { method: "POST", body: "{}" }).catch(() => undefined);
    router.replace("/login");
  }

  if (loading) {
    return <main className="center-state">Loading your workspace…</main>;
  }

  if (!me) {
    return (
      <main className="center-state">
        <p>{error || "Your session could not be loaded."}</p>
        <button className="primary-button" onClick={() => router.replace("/login")}>Return to login</button>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark small">✓</span> TaskFlow</div>
        <div className="profile">
          {me.avatar_url ? (
            // Google supplies this URL; a plain img avoids configuring every Google image hostname.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={me.avatar_url} alt="" className="avatar" referrerPolicy="no-referrer" />
          ) : (
            <span className="avatar fallback">{me.name.charAt(0).toUpperCase()}</span>
          )}
          <div><strong>{me.name}</strong><small>{me.email}</small></div>
          <button className="text-button" onClick={logout}>Log out</button>
        </div>
      </header>

      <section className="dashboard-header">
        <div>
          <p className="eyebrow">YOUR WORKSPACE</p>
          <h1>Tasks</h1>
          <p>Track the work you own and the work assigned to you.</p>
        </div>
        <button className="primary-button" onClick={() => setShowForm((value) => !value)}>
          {showForm ? "Close form" : "+ Create task"}
        </button>
      </section>

      {error && <p className="alert error" role="alert">{error}</p>}
      {notice && <p className="alert success" role="status">{notice}</p>}

      {showForm && (
        <section className="panel create-panel">
          <div>
            <p className="eyebrow">NEW TASK</p>
            <h2>What needs to get done?</h2>
          </div>
          <form onSubmit={createTask}>
            <label>
              Title
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                maxLength={200}
                required
                placeholder="e.g. Prepare launch brief"
              />
            </label>
            <label>
              Description
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                maxLength={5000}
                rows={4}
                placeholder="Add useful context and expected outcome"
              />
            </label>
            <label>
              Assign to
              <select value={assignedTo} onChange={(event) => setAssignedTo(event.target.value)} required>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>{user.name} — {user.email}</option>
                ))}
              </select>
            </label>
            <button className="primary-button" type="submit" disabled={saving || users.length === 0}>
              {saving ? "Creating…" : "Create task"}
            </button>
          </form>
        </section>
      )}

      <nav className="filters" aria-label="Task filters">
        {(["all", "assigned", "created", "pending", "completed"] as Filter[]).map((option) => (
          <button
            key={option}
            className={filter === option ? "active" : ""}
            onClick={() => setFilter(option)}
          >
            {option.charAt(0).toUpperCase() + option.slice(1)}
          </button>
        ))}
      </nav>

      <section className="task-grid">
        {filteredTasks.length === 0 ? (
          <div className="empty-state">
            <span aria-hidden="true">✓</span>
            <h2>No tasks here</h2>
            <p>Create a task or choose another filter.</p>
          </div>
        ) : (
          filteredTasks.map((task) => {
            const canComplete =
              task.status === "pending" && (task.assigned_to === me.id || task.created_by === me.id);
            return (
              <article className="task-card" key={task.id}>
                <div className="task-card-top">
                  <span className={`status ${task.status}`}>{task.status}</span>
                  <time>{new Date(task.created_at).toLocaleDateString()}</time>
                </div>
                <h2>{task.title}</h2>
                <p className="description">{task.description || "No description provided."}</p>
                <dl>
                  <div><dt>Created by</dt><dd>{task.creator_name}</dd></div>
                  <div><dt>Assigned to</dt><dd>{task.assignee_name}</dd></div>
                  {task.completed_at && (
                    <div><dt>Completed</dt><dd>{new Date(task.completed_at).toLocaleString()}</dd></div>
                  )}
                </dl>
                {canComplete && (
                  <button
                    className="complete-button"
                    onClick={() => completeTask(task.id)}
                    disabled={completing === task.id}
                  >
                    {completing === task.id ? "Completing…" : "Mark complete"}
                  </button>
                )}
              </article>
            );
          })
        )}
      </section>
    </main>
  );
}
