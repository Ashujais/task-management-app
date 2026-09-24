export type User = {
  id: string;
  name: string;
  email: string;
  avatar_url: string | null;
};

export type Task = {
  id: string;
  title: string;
  description: string;
  created_by: string;
  assigned_to: string;
  creator_name: string;
  creator_email: string;
  assignee_name: string;
  assignee_email: string;
  status: "pending" | "completed";
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

type ApiError = { error?: string };

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/backend-api${path.replace(/^\/api/, "")}`, {
    ...options,
    credentials: "include",
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  const data = (await response.json().catch(() => ({}))) as T & ApiError;
  if (!response.ok) {
    throw new Error(data.error || "The request failed. Please try again.");
  }
  return data;
}
