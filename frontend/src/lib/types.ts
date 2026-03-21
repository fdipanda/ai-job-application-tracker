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
}
