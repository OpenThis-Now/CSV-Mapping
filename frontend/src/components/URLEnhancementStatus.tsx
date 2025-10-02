import React from "react";

type URLEnhancementStats = {
  totalUrls: number;
  queued: number;
  processing: number;
  completed: number;
  errors: number;
};

function cx(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(" ");
}

function Stat({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <div className="text-center">
      <div className={cx("text-lg font-semibold", color)}>{value}</div>
      <div className="text-xs text-slate-600">{label}</div>
    </div>
  );
}

export default function URLEnhancementStatus({
  stats = { totalUrls: 0, queued: 0, processing: 0, completed: 0, errors: 0 },
}: { stats?: URLEnhancementStats }) {
  const { totalUrls, queued, processing, completed, errors } = stats;
  const progressPct = totalUrls > 0 ? Math.round((completed / totalUrls) * 100) : 0;

  if (totalUrls === 0) {
    return null;
  }

  return (
    <section
      aria-label="URL Enhancement Progress"
      className="rounded-lg border border-slate-200 bg-white shadow-sm p-3 mb-4"
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <div className="animate-spin rounded-full h-4 w-4 border-b border-blue-600"></div>
        <h3 className="text-sm font-medium text-slate-900">URL Enhancement in Progress</h3>
      </div>

      {/* Stats grid - Compact version */}
      <div className="grid grid-cols-5 gap-3 mb-3">
        <Stat value={totalUrls} label="Total URLs" color="text-slate-900" />
        <Stat value={queued} label="Queued" color="text-blue-600" />
        <Stat value={processing} label="Processing" color="text-amber-600" />
        <Stat value={completed} label="Completed" color="text-green-600" />
        <Stat value={errors} label="Errors" color="text-red-600" />
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="h-1.5 w-full rounded-full bg-blue-100">
          <div
            className="h-1.5 rounded-full bg-blue-600 transition-all duration-300"
            style={{ width: `${progressPct}%` }}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressPct}
            role="progressbar"
            aria-label="URL Enhancement progress"
          />
        </div>
        <p className="text-xs text-slate-600 text-center">{progressPct}% completed</p>
      </div>
    </section>
  );
}
