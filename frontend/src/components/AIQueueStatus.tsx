import React from "react";

type Stats = {
  queued: number;
  processing: number;
  ready: number;        // Ready for review
  autoApproved: number; // Auto-approved
};

function cx(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(" ");
}

function Stat({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <div className="text-center">
      <div className={cx("text-3xl font-bold", color)}>{value}</div>
      <div className="mt-1 text-sm text-slate-700">{label}</div>
    </div>
  );
}

export default function AIQueueStatus({
  stats = { queued: 7, processing: 2, ready: 6, autoApproved: 3 },
}: { stats?: Stats }) {
  const total = stats.queued + stats.processing + stats.ready + stats.autoApproved;
  const progressPct = Math.round(((stats.ready + stats.autoApproved) / (total || 1)) * 100);

  return (
    <section
      aria-label="AI queue"
      className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 md:p-6"
    >
      {/* Stats grid */}
      <div className="grid grid-cols-5 gap-6">
        <Stat value={stats.queued}        label="Queued"            color="text-blue-700" />
        <Stat value={stats.processing}    label="Processing"        color="text-amber-700" />
        <Stat value={stats.ready}         label="Ready for review"  color="text-green-700" />
        <Stat value={stats.autoApproved}  label="Auto-approved"     color="text-emerald-700" />
        <Stat value={total}               label="Total"             color="text-slate-900" />
      </div>

      {/* Progress */}
      <div className="mt-4">
        <div className="h-2 w-full rounded-full bg-blue-100">
          <div
            className="h-2 rounded-full bg-blue-600"
            style={{ width: `${progressPct}%` }}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressPct}
            role="progressbar"
            aria-label="Completion progress"
          />
        </div>
        <p className="mt-1 text-sm text-slate-700">{progressPct}% completed</p>
      </div>
    </section>
  );
}
