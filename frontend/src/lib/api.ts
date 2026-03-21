import {
  Application,
  ApplicationCreateInput,
  EmailSyncSummary,
  ApplicationUpdateInput,
} from "@/lib/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export async function getApplications(): Promise<Application[]> {
  const res = await fetch(`${API_BASE}/applications`, { cache: "no-store" });

  if (!res.ok) {
    throw new Error("Failed to fetch applications");
  }

  return res.json();
}

export async function createApplication(
  application: ApplicationCreateInput,
): Promise<Application> {
  const res = await fetch(`${API_BASE}/applications`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(application),
  });

  if (!res.ok) {
    throw new Error("Failed to create application");
  }

  return res.json();
}

export async function deleteApplication(id: number) {
  const res = await fetch(`${API_BASE}/applications/${id}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    throw new Error("Failed to delete application");
  }

  return res.json();
}

export async function updateApplication(
  id: number,
  updates: ApplicationUpdateInput,
): Promise<Application> {
  const res = await fetch(`${API_BASE}/applications/${id}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(updates),
  });

  if (!res.ok) {
    throw new Error("Failed to update application");
  }

  return res.json();
}

export async function syncNewEmails(): Promise<EmailSyncSummary> {
  const res = await fetch(`${API_BASE}/emails/sync-new`, {
    method: "POST",
  });

  if (!res.ok) {
    throw new Error("Failed to sync new emails");
  }

  return res.json();
}
