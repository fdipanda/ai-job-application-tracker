import { STATUS_ORDER, STATUS_STYLES } from "@/lib/status";
import { Application, ApplicationStatus } from "@/lib/types";

function formatLastUpdated(dateString: string) {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  let diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays < 0) diffDays = 0;

  if (diffDays === 0) return "Updated today";
  if (diffDays === 1) return "Updated yesterday";
  if (diffDays < 7) return `Updated ${diffDays} days ago`;

  return `Updated on ${date.toLocaleDateString()}`;
}

export default function ApplicationCard({
  app,
  onDeleted,
  onStatusChange,
}: {
  app: Application;
  onDeleted: (id: number) => void;
  onStatusChange: (id: number, status: ApplicationStatus) => void;
}) {
  function handleDelete() {
    onDeleted(app.id);
  }

  function handleStatusChange(nextStatus: ApplicationStatus) {
    onStatusChange(app.id, nextStatus);
  }

  return (
    <article className="group rounded-[28px] border border-white/80 bg-white/90 p-5 shadow-[0_20px_55px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-1 hover:shadow-[0_24px_70px_rgba(15,23,42,0.14)]">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            {app.location || "Location pending"}
          </p>
          <h3 className="mt-2 text-xl font-semibold text-slate-950">{app.company}</h3>
          <p className="mt-1 text-sm text-slate-600">{app.role}</p>
        </div>

        <span
          className={`inline-flex shrink-0 rounded-full border px-3 py-1 text-xs font-semibold ${STATUS_STYLES[app.status]}`}
        >
          {app.status}
        </span>
      </div>

      <div className="mt-5 rounded-2xl bg-slate-50 p-4">
        <div className="flex items-center justify-between gap-3">
          <label className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            Move stage
          </label>
          <p className="text-xs text-slate-500">{formatLastUpdated(app.last_updated)}</p>
        </div>

        <select
          value={app.status}
          onChange={(event) => handleStatusChange(event.target.value as ApplicationStatus)}
          className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-sky-400 focus:ring-4 focus:ring-sky-100"
        >
          {STATUS_ORDER.map((statusOption) => (
            <option key={statusOption} value={statusOption}>
              {statusOption}
            </option>
          ))}
        </select>
      </div>

      {app.notes && (
        <p className="mt-4 rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
          {app.notes}
        </p>
      )}

      <div className="mt-5 flex items-center justify-between gap-3 border-t border-slate-100 pt-4">
        <div className="text-xs text-slate-400">
          Applied {new Date(app.date_applied).toLocaleDateString()}
        </div>

        <button
          onClick={handleDelete}
          className="rounded-full border border-rose-200 px-3 py-2 text-sm font-semibold text-rose-600 transition hover:border-rose-300 hover:bg-rose-50"
        >
          Delete
        </button>
      </div>
    </article>
  );
}
