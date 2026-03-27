export const APPLICATION_STATUSES = [
  "Wishlist",
  "Applied",
  "Recruiter Contact",
  "Assessment",
  "Interview",
  "Final Interview",
  "Offer",
  "Rejected",
  "Withdrawn",
] as const;

export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number];

export interface Application {
  id: number;
  company: string;
  role: string;
  status: ApplicationStatus;
  location?: string;
  application_link?: string;
  notes?: string;
  date_applied: string;
  last_updated: string;
}

export interface ApplicationCreateInput {
  company: string;
  role: string;
  status: ApplicationStatus;
  location?: string;
  application_link?: string;
  notes?: string;
}

export interface ApplicationUpdateInput {
  company?: string;
  role?: string;
  status?: ApplicationStatus;
  location?: string;
  application_link?: string;
  notes?: string;
}

export interface EmailSyncSummary {
  scanned_count: number;
  detected_count: number;
  added_count: number;
  updated_count: number;
  skipped_count: number;
  write_failures: number;
  checkpoint_at?: string | null;
  last_run_status: string;
  audit_log_path?: string | null;
  run_id?: string | null;
}

export interface BacklogJobStartResponse {
  job_id: string;
  status: "running" | "completed" | "failed";
  max_pages: number;
}

export interface BacklogJobStatus {
  job_id: string;
  status: "running" | "completed" | "failed";
  max_pages: number;
  pages_processed: number;
  emails_scanned: number;
  applications_processed: number;
  write_failures: number;
  percent_complete: number;
  elapsed_seconds: number;
  eta_seconds?: number | null;
  run_id?: string | null;
  audit_log_path?: string | null;
  error_message?: string | null;
}

export interface AuthStatus {
  authenticated: boolean;
}
