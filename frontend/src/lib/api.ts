import {
  Application,
  ApplicationCreateInput,
  AuthStatus,
  BacklogJobStartResponse,
  BacklogJobStatus,
  EmailSyncSummary,
  ApplicationUpdateInput,
} from "@/lib/types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export function getOutlookLoginUrl(): string {
  // OAuth login is a browser redirect, so the UI needs the raw URL instead of a fetch wrapper.
  return `${API_BASE}/auth/login`;
}

export async function getAuthStatus(): Promise<AuthStatus> {
  const res = await fetch(`${API_BASE}/auth/status`, { cache: "no-store" });

  if (!res.ok) {
    throw new Error(await extractErrorMessage(res, "Failed to fetch Outlook auth status"));
  }

  return res.json();
}

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
    throw new Error(await extractErrorMessage(res, "Failed to sync new emails"));
  }

  return res.json();
}

export async function startBacklogProcessing(maxPages: number): Promise<BacklogJobStartResponse> {
  const res = await fetch(`${API_BASE}/emails/process-backlog`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ max_pages: maxPages }),
  });

  if (!res.ok) {
    throw new Error(await extractErrorMessage(res, "Failed to start backlog processing"));
  }

  return res.json();
}

export async function getBacklogJobStatus(jobId: string): Promise<BacklogJobStatus> {
  const res = await fetch(`${API_BASE}/emails/process-backlog/${jobId}`, {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(await extractErrorMessage(res, "Failed to fetch backlog job status"));
  }

  return res.json();
}

async function extractErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    // Most backend errors come back in FastAPI's {"detail": "..."} shape.
    const payload = await res.json() as { detail?: string };
    return payload.detail ?? fallback;
  } catch {
    return fallback;
  }
}
