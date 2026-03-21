import { APPLICATION_STATUSES, Application, ApplicationStatus } from "@/lib/types";

export const STATUS_ORDER = APPLICATION_STATUSES;
export const STATUS_FILTER_OPTIONS = ["All", ...STATUS_ORDER] as const;

export type StatusFilter = (typeof STATUS_FILTER_OPTIONS)[number];
export type SortOption = "date" | "company" | "status";

export const STATUS_STYLES: Record<ApplicationStatus, string> = {
  Wishlist: "border-stone-300 bg-stone-100 text-stone-700",
  Applied: "border-sky-300 bg-sky-100 text-sky-700",
  "Recruiter Contact": "border-cyan-300 bg-cyan-100 text-cyan-700",
  Assessment: "border-indigo-300 bg-indigo-100 text-indigo-700",
  Interview: "border-amber-300 bg-amber-100 text-amber-700",
  "Final Interview": "border-orange-300 bg-orange-100 text-orange-700",
  Offer: "border-emerald-300 bg-emerald-100 text-emerald-700",
  Rejected: "border-rose-300 bg-rose-100 text-rose-700",
  Withdrawn: "border-slate-300 bg-slate-200 text-slate-700",
};

export const STATUS_DOT_STYLES: Record<ApplicationStatus, string> = {
  Wishlist: "border-stone-300 bg-stone-400",
  Applied: "border-sky-300 bg-sky-400",
  "Recruiter Contact": "border-cyan-300 bg-cyan-400",
  Assessment: "border-indigo-300 bg-indigo-400",
  Interview: "border-amber-300 bg-amber-400",
  "Final Interview": "border-orange-300 bg-orange-400",
  Offer: "border-emerald-300 bg-emerald-400",
  Rejected: "border-rose-300 bg-rose-400",
  Withdrawn: "border-slate-300 bg-slate-400",
};

export const STATUS_SHORT_LABELS: Record<ApplicationStatus, string> = {
  Wishlist: "Wishlist",
  Applied: "Applied",
  "Recruiter Contact": "Recruiter",
  Assessment: "Assessment",
  Interview: "Interview",
  "Final Interview": "Final",
  Offer: "Offer",
  Rejected: "Rejected",
  Withdrawn: "Withdrawn",
};

export function getStatusIndex(status: ApplicationStatus) {
  return STATUS_ORDER.indexOf(status);
}

export function sortApplications(applications: Application[], sortBy: SortOption) {
  return [...applications].sort((left, right) => {
    if (sortBy === "company") {
      return left.company.localeCompare(right.company);
    }

    if (sortBy === "status") {
      return getStatusIndex(left.status) - getStatusIndex(right.status);
    }

    return (
      new Date(right.date_applied).getTime() - new Date(left.date_applied).getTime()
    );
  });
}
