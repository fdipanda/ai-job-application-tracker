"use client";

import { useEffect, useMemo, useState } from "react";

import AddApplicationForm from "@/components/AddApplicationForm";
import ApplicationCard from "@/components/ApplicationCard";
import {
  deleteApplication,
  getApplications,
  syncNewEmails,
  updateApplication,
} from "@/lib/api";
import {
  getStatusIndex,
  sortApplications,
  STATUS_DOT_STYLES,
  STATUS_FILTER_OPTIONS,
  STATUS_SHORT_LABELS,
  StatusFilter,
  SortOption,
} from "@/lib/status";
import { Application, ApplicationStatus, EmailSyncSummary } from "@/lib/types";

const SUMMARY_CARDS = [
  {
    label: "Tracked",
    description: "Applications in the board",
    valueKey: "total",
  },
  {
    label: "Active",
    description: "Still moving through pipeline",
    valueKey: "active",
  },
  {
    label: "Late Stage",
    description: "Interview through offer",
    valueKey: "lateStage",
  },
  {
    label: "Closed",
    description: "Rejected or withdrawn",
    valueKey: "closed",
  },
] as const;

export default function Home() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<StatusFilter>("All");
  const [sortBy, setSortBy] = useState<SortOption>("date");
  const [isLoading, setIsLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncSummary, setSyncSummary] = useState<EmailSyncSummary | null>(null);

  async function loadApplications() {
    setIsLoading(true);
    setError(null);

    try {
      const data = await getApplications();
      setApplications(data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load applications");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadApplications();
  }, []);

  const countsByStatus = useMemo(() => {
    return applications.reduce<Record<ApplicationStatus, number>>((counts, application) => {
      counts[application.status] += 1;
      return counts;
    }, {
      Wishlist: 0,
      Applied: 0,
      "Recruiter Contact": 0,
      Assessment: 0,
      Interview: 0,
      "Final Interview": 0,
      Offer: 0,
      Rejected: 0,
      Withdrawn: 0,
    });
  }, [applications]);

  const summaryValues = useMemo(() => {
    const active = applications.filter(
      (application) => !["Rejected", "Withdrawn", "Offer"].includes(application.status),
    ).length;
    const lateStage = applications.filter(
      (application) => getStatusIndex(application.status) >= getStatusIndex("Interview") &&
        getStatusIndex(application.status) <= getStatusIndex("Offer"),
    ).length;
    const closed = applications.filter((application) =>
      ["Rejected", "Withdrawn"].includes(application.status),
    ).length;

    return {
      total: applications.length,
      active,
      lateStage,
      closed,
    };
  }, [applications]);

  const filteredApplications = useMemo(() => {
    const searched = applications
      .filter((application) => {
        const needle = search.trim().toLowerCase();
        if (!needle) {
          return true;
        }

        return (
          application.company.toLowerCase().includes(needle) ||
          application.role.toLowerCase().includes(needle) ||
          (application.location ?? "").toLowerCase().includes(needle)
        );
      })
      .filter((application) =>
        filterStatus === "All" ? true : application.status === filterStatus,
      );

    return sortApplications(searched, sortBy);
  }, [applications, filterStatus, search, sortBy]);

  function handleCreateApplication(application: Application) {
    setApplications((current) => sortApplications([application, ...current], sortBy));
  }

  async function handleDeleteApplication(id: number) {
    const previousApplications = applications;
    setApplications((current) => current.filter((application) => application.id !== id));

    try {
      await deleteApplication(id);
    } catch (deleteError) {
      setApplications(previousApplications);
      setError(deleteError instanceof Error ? deleteError.message : "Failed to delete application");
    }
  }

  async function handleStatusChange(id: number, nextStatus: ApplicationStatus) {
    const previousApplications = applications;

    setApplications((current) =>
      current.map((application) =>
        application.id === id
          ? {
              ...application,
              status: nextStatus,
              last_updated: new Date().toISOString(),
            }
          : application,
      ),
    );

    try {
      const updated = await updateApplication(id, { status: nextStatus });
      setApplications((current) =>
        current.map((application) => (application.id === id ? updated : application)),
      );
    } catch (updateError) {
      setApplications(previousApplications);
      setError(updateError instanceof Error ? updateError.message : "Failed to update application");
    }
  }

  async function handleSyncNewEmails() {
    setIsSyncing(true);
    setError(null);

    try {
      const summary = await syncNewEmails();
      setSyncSummary(summary);
      await loadApplications();
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : "Failed to sync new emails");
    } finally {
      setIsSyncing(false);
    }
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(125,211,252,0.24),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(167,243,208,0.3),_transparent_28%),linear-gradient(180deg,_#f8fafc_0%,_#eef2f7_100%)] px-4 py-8 text-slate-900 sm:px-6 lg:px-10">
      <div className="mx-auto max-w-7xl">
        <section className="rounded-[36px] border border-white/70 bg-white/78 p-6 shadow-[0_30px_80px_rgba(15,23,42,0.1)] backdrop-blur sm:p-8">
          <div className="grid gap-8 xl:grid-cols-[1.3fr_0.9fr]">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.28em] text-sky-700">
                Application Command Center
              </p>
              <h1 className="mt-4 max-w-3xl text-4xl font-semibold tracking-tight text-slate-950 sm:text-5xl">
                Track the full hiring pipeline with less drift and faster updates.
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
                Review momentum at a glance, filter every status the backend supports, and
                keep each application moving without reloading the whole dashboard.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              {SUMMARY_CARDS.map((card) => (
                <div
                  key={card.label}
                  className="rounded-[28px] border border-slate-200/80 bg-slate-50/80 p-5"
                >
                  <p className="text-sm font-medium text-slate-500">{card.label}</p>
                  <p className="mt-3 text-3xl font-semibold text-slate-950">
                    {summaryValues[card.valueKey]}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">{card.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mt-6">
          <AddApplicationForm onCreated={handleCreateApplication} />
        </section>

        <section className="mt-6 rounded-[32px] border border-white/70 bg-white/82 p-5 shadow-[0_24px_70px_rgba(15,23,42,0.08)] backdrop-blur">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.22em] text-slate-400">
                Pipeline views
              </p>
              <h2 className="mt-2 text-2xl font-semibold text-slate-950">
                Filter and scan by stage
              </h2>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              <button
                onClick={handleSyncNewEmails}
                disabled={isSyncing}
                className="rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {isSyncing ? "Scanning..." : "Scan New Emails"}
              </button>

              <input
                type="text"
                placeholder="Search company, role, or location..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-sky-400 focus:ring-4 focus:ring-sky-100 sm:w-80"
              />

              <select
                value={sortBy}
                onChange={(event) => setSortBy(event.target.value as SortOption)}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-sky-400 focus:ring-4 focus:ring-sky-100"
              >
                <option value="date">Newest first</option>
                <option value="company">Company A-Z</option>
                <option value="status">Pipeline order</option>
              </select>
            </div>
          </div>

          <div className="mt-5 flex gap-2 overflow-x-auto pb-1">
            {STATUS_FILTER_OPTIONS.map((statusOption) => {
              const isActive = filterStatus === statusOption;
              const count =
                statusOption === "All"
                  ? applications.length
                  : countsByStatus[statusOption as ApplicationStatus];

              return (
                <button
                  key={statusOption}
                  onClick={() => setFilterStatus(statusOption)}
                  className={`inline-flex shrink-0 items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold transition ${
                    isActive
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  {statusOption !== "All" && (
                    <span
                      className={`h-2.5 w-2.5 rounded-full border ${
                        isActive ? "border-white/60 bg-white" : STATUS_DOT_STYLES[statusOption]
                      }`}
                    />
                  )}
                  <span>
                    {statusOption === "All"
                      ? "All"
                      : STATUS_SHORT_LABELS[statusOption as ApplicationStatus]}
                  </span>
                  <span className={`rounded-full px-2 py-0.5 text-xs ${isActive ? "bg-white/15 text-white" : "bg-slate-100 text-slate-500"}`}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        {error && (
          <div className="mt-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        {syncSummary && (
          <div className="mt-6 rounded-[28px] border border-emerald-200 bg-emerald-50/80 p-5 text-sm text-emerald-900 shadow-[0_16px_40px_rgba(16,185,129,0.08)]">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-700">
                  Latest email sync
                </p>
                <h3 className="mt-2 text-xl font-semibold">
                  {syncSummary.added_count} added, {syncSummary.updated_count} updated
                </h3>
                <p className="mt-1 text-emerald-800/80">
                  Scanned {syncSummary.scanned_count} new emails and detected{" "}
                  {syncSummary.detected_count} likely job messages.
                </p>
              </div>

              <div className="text-sm text-emerald-900/80">
                {syncSummary.checkpoint_at
                  ? `Checkpoint saved at ${new Date(syncSummary.checkpoint_at).toLocaleString()}`
                  : "No checkpoint saved yet"}
              </div>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-4">
              <div className="rounded-2xl bg-white/80 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">
                  Scanned
                </p>
                <p className="mt-2 text-2xl font-semibold">{syncSummary.scanned_count}</p>
              </div>
              <div className="rounded-2xl bg-white/80 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">
                  Detected
                </p>
                <p className="mt-2 text-2xl font-semibold">{syncSummary.detected_count}</p>
              </div>
              <div className="rounded-2xl bg-white/80 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">
                  Added / Updated
                </p>
                <p className="mt-2 text-2xl font-semibold">
                  {syncSummary.added_count} / {syncSummary.updated_count}
                </p>
              </div>
              <div className="rounded-2xl bg-white/80 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">
                  Skipped
                </p>
                <p className="mt-2 text-2xl font-semibold">{syncSummary.skipped_count}</p>
              </div>
            </div>
          </div>
        )}

        <section className="mt-6">
          {isLoading ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, index) => (
                <div
                  key={index}
                  className="h-64 animate-pulse rounded-[28px] border border-white/80 bg-white/70"
                />
              ))}
            </div>
          ) : filteredApplications.length === 0 ? (
            <div className="rounded-[32px] border border-dashed border-slate-300 bg-white/70 px-6 py-14 text-center shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
              <p className="text-lg font-semibold text-slate-900">No applications match this view.</p>
              <p className="mt-2 text-sm text-slate-500">
                Try a different status chip, clear the search, or add a new application above.
              </p>
            </div>
          ) : (
            <>
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.22em] text-slate-400">
                    Results
                  </p>
                  <h2 className="mt-1 text-2xl font-semibold text-slate-950">
                    {filteredApplications.length} application
                    {filteredApplications.length === 1 ? "" : "s"} visible
                  </h2>
                </div>
              </div>

              <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
                {filteredApplications.map((application) => (
                  <ApplicationCard
                    key={application.id}
                    app={application}
                    onDeleted={handleDeleteApplication}
                    onStatusChange={handleStatusChange}
                  />
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
