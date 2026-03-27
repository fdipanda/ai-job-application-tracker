"use client";

import { useEffect, useMemo, useState } from "react";

import AddApplicationForm from "@/components/AddApplicationForm";
import ApplicationCard from "@/components/ApplicationCard";
import {
  getAuthStatus,
  deleteApplication,
  getBacklogJobStatus,
  getApplications,
  getOutlookLoginUrl,
  startBacklogProcessing,
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
import {
  Application,
  ApplicationStatus,
  AuthStatus,
  BacklogJobStatus,
  EmailSyncSummary,
} from "@/lib/types";

const BACKLOG_PRESETS = [20, 50, 100] as const;

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
  // This component acts like the page-level "orchestrator".
  // In C# / ASP.NET terms, think of it as the place coordinating multiple DTO/API calls
  // and passing the resulting state down into smaller view components.
  const [applications, setApplications] = useState<Application[]>([]);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<StatusFilter>("All");
  const [sortBy, setSortBy] = useState<SortOption>("date");
  const [isLoading, setIsLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isStartingBacklog, setIsStartingBacklog] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncSummary, setSyncSummary] = useState<EmailSyncSummary | null>(null);
  const [backlogMaxPages, setBacklogMaxPages] = useState(20);
  const [backlogJob, setBacklogJob] = useState<BacklogJobStatus | null>(null);
  const [lastCompletedBacklogJobId, setLastCompletedBacklogJobId] = useState<string | null>(null);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [isAuthStatusLoading, setIsAuthStatusLoading] = useState(true);
  const [authBanner, setAuthBanner] = useState<string | null>(null);
  const [isAdvancedSyncOpen, setIsAdvancedSyncOpen] = useState(false);

  async function loadAuthStatus() {
    setIsAuthStatusLoading(true);

    try {
      const status = await getAuthStatus();
      setAuthStatus(status);
    } catch (authError) {
      setAuthStatus({ authenticated: false });
      setError(authError instanceof Error ? authError.message : "Failed to load Outlook status");
    } finally {
      setIsAuthStatusLoading(false);
    }
  }

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
    // Initial data load for the dashboard itself.
    loadApplications();
  }, []);

  useEffect(() => {
    // Load Outlook connection state independently so email controls can render correctly.
    void loadAuthStatus();
  }, []);

  useEffect(() => {
    // The OAuth callback redirects back to the frontend with a query-string flag.
    // We read it once, show feedback, then remove it from the URL so refreshes stay clean.
    const params = new URLSearchParams(window.location.search);
    const outlookState = params.get("outlook");

    if (!outlookState) {
      return;
    }

    if (outlookState === "connected") {
      setAuthBanner("Outlook connected successfully.");
      setAuthStatus({ authenticated: true });
      void loadAuthStatus();
    } else if (outlookState === "error") {
      setAuthBanner("Outlook connection failed. Please try again.");
    }

    params.delete("outlook");
    const nextQuery = params.toString();
    const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ""}${window.location.hash}`;
    window.history.replaceState({}, "", nextUrl);
  }, []);

  useEffect(() => {
    if (!backlogJob || backlogJob.status !== "running") {
      return;
    }

    // Polling is the simplest way for the page to keep a progress bar up to date
    // without introducing WebSockets or server-sent events.
    const pollJob = async () => {
      try {
        const nextJob = await getBacklogJobStatus(backlogJob.job_id);
        setBacklogJob(nextJob);
      } catch (pollError) {
        setError(
          pollError instanceof Error
            ? pollError.message
            : "Failed to fetch backlog job status",
        );
      }
    };

    const intervalId = window.setInterval(pollJob, 2500);
    void pollJob();

    return () => window.clearInterval(intervalId);
  }, [backlogJob]);

  useEffect(() => {
    if (!backlogJob || backlogJob.status !== "completed") {
      return;
    }

    if (lastCompletedBacklogJobId === backlogJob.job_id) {
      return;
    }

    setLastCompletedBacklogJobId(backlogJob.job_id);
    void loadApplications();
  }, [backlogJob, lastCompletedBacklogJobId]);

  const countsByStatus = useMemo(() => {
    // Derived state: this is recalculated from the source list instead of stored separately.
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
    // Search/filter/sort are kept client-side because the dataset is still small enough
    // that the UI can do this cheaply after one API fetch.
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

    // Optimistic UI update: show the new status immediately, then roll back if the API fails.
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
    if (!authStatus?.authenticated) {
      return;
    }

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

  async function handleStartBacklogProcessing() {
    if (!authStatus?.authenticated) {
      return;
    }

    setIsStartingBacklog(true);
    setError(null);

    try {
      const job = await startBacklogProcessing(backlogMaxPages);
      // Seed the job state immediately so the progress UI can render before polling returns.
      setBacklogJob({
        job_id: job.job_id,
        status: job.status,
        max_pages: job.max_pages,
        pages_processed: 0,
        emails_scanned: 0,
        applications_processed: 0,
        write_failures: 0,
        percent_complete: 0,
        elapsed_seconds: 0,
        eta_seconds: null,
        run_id: null,
        audit_log_path: null,
        error_message: null,
      });
    } catch (backlogError) {
      setError(
        backlogError instanceof Error
          ? backlogError.message
          : "Failed to start backlog processing",
      );
    } finally {
      setIsStartingBacklog(false);
    }
  }

  const isBacklogRunning = backlogJob?.status === "running";
  const isSyncBusy = isSyncing || isBacklogRunning || isStartingBacklog;
  const isOutlookConnected = authStatus?.authenticated ?? false;
  // This single flag keeps the button enable/disable rules readable in the JSX below.
  const isEmailActionsDisabled = isSyncBusy || !isOutlookConnected;

  function handleConnectOutlook() {
    window.location.href = getOutlookLoginUrl();
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(125,211,252,0.24),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(167,243,208,0.3),_transparent_28%),linear-gradient(180deg,_#f8fafc_0%,_#eef2f7_100%)] px-4 py-8 text-slate-900 sm:px-6 lg:px-10">
      <div className="mx-auto max-w-7xl">
        <section className="rounded-[36px] border border-white/70 bg-white/78 p-6 shadow-[0_30px_80px_rgba(15,23,42,0.1)] backdrop-blur sm:p-8">
          <div className="grid gap-6 xl:grid-cols-[1.25fr_0.95fr]">
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
              <div className="mt-6 flex flex-col gap-4 lg:max-w-2xl">
                <div className="w-full rounded-[24px] border border-slate-200/80 bg-slate-50/90 p-4 shadow-[0_12px_35px_rgba(15,23,42,0.05)]">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                        Outlook Status
                      </p>
                      <p className="mt-1 text-base font-semibold text-slate-950">
                        {isAuthStatusLoading
                          ? "Checking connection..."
                          : isOutlookConnected
                            ? "Outlook connected"
                            : "Outlook not connected"}
                      </p>
                      <p className="mt-1 text-sm text-slate-600">
                        {isOutlookConnected
                          ? "Email sync and backlog processing are ready to use."
                          : "Connect Outlook to enable email syncing and backlog imports."}
                      </p>
                    </div>

                    <button
                      onClick={handleConnectOutlook}
                      disabled={isAuthStatusLoading}
                      className="rounded-2xl bg-sky-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-300"
                    >
                      {isOutlookConnected ? "Reconnect Outlook" : "Connect Outlook"}
                    </button>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setIsAdvancedSyncOpen((current) => !current)}
                  className="inline-flex w-full items-center justify-between rounded-[22px] border border-sky-200/80 bg-white/85 px-4 py-3 text-left shadow-[0_12px_35px_rgba(14,116,144,0.08)] transition hover:border-sky-300 hover:bg-white"
                >
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-700">
                      Advanced Email Sync
                    </p>
                    <p className="mt-1 text-sm text-slate-600">
                      Run longer historical scans and future advanced sync tools from here.
                    </p>
                  </div>
                  <span className="rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold text-sky-700">
                    {isAdvancedSyncOpen ? "Close" : "Open"}
                  </span>
                </button>

                {isAdvancedSyncOpen && (
                  <div className="mt-3 w-full rounded-[26px] border border-sky-100 bg-[linear-gradient(135deg,rgba(240,249,255,0.98),rgba(236,253,245,0.96))] p-4 shadow-[0_20px_60px_rgba(14,116,144,0.14)]">
                    <div className="flex flex-col gap-4">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">
                          Advanced Email Sync
                        </p>
                        <h2 className="mt-2 text-xl font-semibold text-slate-950">
                          Historical scans and deeper sync controls
                        </h2>
                        <p className="mt-2 text-sm leading-6 text-slate-600">
                          Backlog scans review older inbox pages and may take longer than
                          regular sync. This panel is ready for future advanced tools too.
                        </p>
                      </div>

                      <div className="rounded-[22px] border border-white/80 bg-white/85 p-4 shadow-[0_14px_35px_rgba(15,23,42,0.05)]">
                        <div className="flex flex-col gap-4">
                          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                            <label className="flex-1">
                              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                                Pages to scan
                              </span>
                              <input
                                type="number"
                                min={1}
                                max={100}
                                value={backlogMaxPages}
                                onChange={(event) => setBacklogMaxPages(Number(event.target.value) || 20)}
                                disabled={isEmailActionsDisabled}
                                className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-sky-400 focus:ring-4 focus:ring-sky-100 disabled:cursor-not-allowed disabled:bg-slate-100"
                              />
                            </label>

                            <button
                              onClick={handleStartBacklogProcessing}
                              disabled={isEmailActionsDisabled}
                              className="rounded-2xl bg-sky-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-300"
                            >
                              {isStartingBacklog || isBacklogRunning
                                ? "Processing..."
                                : "Process Backlog"}
                            </button>
                          </div>

                          <div className="flex flex-wrap gap-2">
                            {BACKLOG_PRESETS.map((preset) => (
                              <button
                                key={preset}
                                type="button"
                                onClick={() => setBacklogMaxPages(preset)}
                                disabled={isEmailActionsDisabled}
                                className={`rounded-full px-3 py-1.5 text-sm font-semibold transition ${
                                  backlogMaxPages === preset
                                    ? "bg-sky-600 text-white"
                                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                                } disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400`}
                              >
                                {preset} pages
                              </button>
                            ))}
                          </div>

                          <p className="text-sm text-slate-600">
                            Process Backlog may take longer than Scan New Emails while it works
                            through older inbox pages.
                          </p>

                          {backlogJob && (
                            <div className="rounded-[24px] border border-sky-100 bg-slate-950 px-4 py-4 text-white">
                              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                <div>
                                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-200">
                                    Backlog job
                                  </p>
                                  <h3 className="mt-2 text-lg font-semibold">
                                    {backlogJob.status === "completed"
                                      ? "Backlog processing complete"
                                      : backlogJob.status === "failed"
                                        ? "Backlog processing failed"
                                        : "Backlog processing is running"}
                                  </h3>
                                </div>
                                <div className="text-sm text-sky-100/90">
                                  Estimated time remaining {formatEta(backlogJob.eta_seconds)}
                                </div>
                              </div>

                              <div className="mt-4 h-3 overflow-hidden rounded-full bg-white/10">
                                <div
                                  className="h-full rounded-full bg-[linear-gradient(90deg,#38bdf8,#34d399)] transition-all duration-500"
                                  style={{ width: `${backlogJob.percent_complete}%` }}
                                />
                              </div>

                              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                                <div className="rounded-2xl bg-white/10 px-4 py-3">
                                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-100/80">
                                    Progress
                                  </p>
                                  <p className="mt-2 text-2xl font-semibold">
                                    {backlogJob.pages_processed} / {backlogJob.max_pages}
                                  </p>
                                  <p className="mt-1 text-sm text-sky-100/80">
                                    {backlogJob.percent_complete}% complete
                                  </p>
                                </div>
                                <div className="rounded-2xl bg-white/10 px-4 py-3">
                                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-100/80">
                                    Emails scanned
                                  </p>
                                  <p className="mt-2 text-2xl font-semibold">{backlogJob.emails_scanned}</p>
                                  <p className="mt-1 text-sm text-sky-100/80">
                                    Elapsed {formatDuration(backlogJob.elapsed_seconds)}
                                  </p>
                                </div>
                                <div className="rounded-2xl bg-white/10 px-4 py-3">
                                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-100/80">
                                    Applications detected
                                  </p>
                                  <p className="mt-2 text-2xl font-semibold">
                                    {backlogJob.applications_processed}
                                  </p>
                                </div>
                                <div className="rounded-2xl bg-white/10 px-4 py-3">
                                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-100/80">
                                    Write failures
                                  </p>
                                  <p className="mt-2 text-2xl font-semibold">{backlogJob.write_failures}</p>
                                </div>
                              </div>

                              {backlogJob.run_id && (
                                <p className="mt-4 text-sm text-sky-100/80">
                                  Run ID {backlogJob.run_id}
                                </p>
                              )}

                              {backlogJob.audit_log_path && (
                                <p className="mt-1 text-sm text-sky-100/80">
                                  Audit log {backlogJob.audit_log_path}
                                </p>
                              )}

                              {backlogJob.error_message && (
                                <p className="mt-4 rounded-2xl border border-rose-300/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-100">
                                  {backlogJob.error_message}
                                </p>
                              )}
                            </div>
                          )}

                          {!isOutlookConnected && !isAuthStatusLoading && (
                            <p className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                              Connect Outlook to enable email syncing.
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
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
                disabled={isEmailActionsDisabled}
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

        {authBanner && (
          <div className="mt-6 rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
            {authBanner}
          </div>
        )}

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

function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;

  if (minutes === 0) {
    return `${remainingSeconds}s`;
  }

  return `${minutes}m ${remainingSeconds}s`;
}

function formatEta(etaSeconds?: number | null): string {
  if (etaSeconds == null) {
    return "calculating...";
  }

  if (etaSeconds === 0) {
    return "about 0s";
  }

  return `about ${formatDuration(etaSeconds)}`;
}
