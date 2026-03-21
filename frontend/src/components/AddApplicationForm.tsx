"use client";

import { FormEvent, useState } from "react";

import { createApplication } from "@/lib/api";
import { STATUS_ORDER } from "@/lib/status";
import { Application, ApplicationStatus } from "@/lib/types";

export default function AddApplicationForm({
  onCreated,
}: {
  onCreated: (application: Application) => void;
}) {
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState<ApplicationStatus>("Applied");
  const [location, setLocation] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);

    try {
      const createdApplication = await createApplication({
        company,
        role,
        status,
        location: location || undefined,
      });

      onCreated(createdApplication);
      setCompany("");
      setRole("");
      setStatus("Applied");
      setLocation("");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-[28px] border border-white/70 bg-white/80 p-5 shadow-[0_18px_60px_rgba(15,23,42,0.08)] backdrop-blur"
    >
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Add application</h2>
          <p className="text-sm text-slate-500">
            Capture a lead manually and keep the pipeline current.
          </p>
        </div>
        <div className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
          Manual entry
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <input
          className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-sky-400 focus:ring-4 focus:ring-sky-100"
          placeholder="Company"
          value={company}
          onChange={(event) => setCompany(event.target.value)}
          required
        />

        <input
          className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-sky-400 focus:ring-4 focus:ring-sky-100"
          placeholder="Role"
          value={role}
          onChange={(event) => setRole(event.target.value)}
          required
        />

        <input
          className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-sky-400 focus:ring-4 focus:ring-sky-100"
          placeholder="Location"
          value={location}
          onChange={(event) => setLocation(event.target.value)}
        />

        <select
          className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-sky-400 focus:ring-4 focus:ring-sky-100"
          value={status}
          onChange={(event) => setStatus(event.target.value as ApplicationStatus)}
        >
          {STATUS_ORDER.map((statusOption) => (
            <option key={statusOption} value={statusOption}>
              {statusOption}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4 flex justify-end">
        <button
          className="rounded-full bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          type="submit"
          disabled={isSubmitting}
        >
          {isSubmitting ? "Saving..." : "Add Application"}
        </button>
      </div>
    </form>
  );
}
