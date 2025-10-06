import React from "react";
import { FileText, Globe, Database } from "lucide-react";

type UnifiedStats = {
  csv: {
    queued: number;
    processing: number;
    completed: number;
    total: number;
  };
  pdf: {
    queued: number;
    processing: number;
    completed: number;
    total: number;
  };
  url: {
    queued: number;
    processing: number;
    completed: number;
    total: number;
  };
  total: {
    queued: number;
    processing: number;
    completed: number;
    total: number;
  };
  hasActivity: boolean;
};

function cx(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(" ");
}

function Stat({ value, label, color, icon }: { value: number; label: string; color: string; icon?: React.ReactNode }) {
  return (
    <div className="text-center">
      <div className="flex items-center justify-center gap-2 mb-1">
        {icon && <div className="text-slate-500">{icon}</div>}
        <div className={cx("text-2xl font-bold", color)}>{value}</div>
      </div>
      <div className="text-xs text-slate-600">{label}</div>
    </div>
  );
}

function ProcessTypeCard({ 
  title, 
  icon, 
  stats, 
  color 
}: { 
  title: string; 
  icon: React.ReactNode; 
  stats: { queued: number; processing: number; completed: number; total: number }; 
  color: string;
}) {
  const progressPct = stats.total > 0 ? Math.round((stats.completed / stats.total) * 100) : 0;
  
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="text-slate-600">{icon}</div>
        <h3 className="font-semibold text-slate-800">{title}</h3>
      </div>
      
      <div className="grid grid-cols-3 gap-3 mb-3">
        <Stat value={stats.queued} label="Queued" color="text-blue-600" />
        <Stat value={stats.processing} label="Processing" color="text-amber-600" />
        <Stat value={stats.completed} label="Completed" color="text-green-600" />
      </div>
      
      {stats.total > 0 && (
        <div>
          <div className="h-1.5 w-full rounded-full bg-slate-100">
            <div
              className={cx("h-1.5 rounded-full", color)}
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-slate-600">{progressPct}% completed</p>
        </div>
      )}
    </div>
  );
}

export default function UnifiedAIStatus({
  stats = {
    csv: { queued: 0, processing: 0, completed: 0, total: 0 },
    pdf: { queued: 0, processing: 0, completed: 0, total: 0 },
    url: { queued: 0, processing: 0, completed: 0, total: 0 },
    total: { queued: 0, processing: 0, completed: 0, total: 0 },
    hasActivity: false
  }
}: { stats?: UnifiedStats }) {
  const totalProgressPct = stats.total.total > 0 ? Math.round((stats.total.completed / stats.total.total) * 100) : 0;

  if (!stats.hasActivity && stats.total.total === 0) {
    return (
      <section
        aria-label="AI Processing Status"
        className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 md:p-6"
      >
        <div className="text-center text-slate-500">
          <Database className="mx-auto h-8 w-8 mb-2" />
          <p className="text-sm">No AI processing activity</p>
        </div>
      </section>
    );
  }

  return (
    <section
      aria-label="AI Processing Status"
      className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 md:p-6"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-800">AI Processing Status</h2>
        <div className="text-sm text-slate-600">
          {stats.total.total} total items
        </div>
      </div>

      {/* Overall Progress */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-slate-700">Overall Progress</span>
          <span className="text-sm text-slate-600">{totalProgressPct}%</span>
        </div>
        <div className="h-2 w-full rounded-full bg-slate-100">
          <div
            className="h-2 rounded-full bg-gradient-to-r from-blue-500 to-green-500"
            style={{ width: `${totalProgressPct}%` }}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={totalProgressPct}
            role="progressbar"
            aria-label="Overall completion progress"
          />
        </div>
      </div>

      {/* Process Type Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ProcessTypeCard
          title="CSV AI Queue"
          icon={<Database className="h-4 w-4" />}
          stats={stats.csv}
          color="bg-blue-500"
        />
        <ProcessTypeCard
          title="PDF Processing"
          icon={<FileText className="h-4 w-4" />}
          stats={stats.pdf}
          color="bg-purple-500"
        />
        <ProcessTypeCard
          title="URL Enhancement"
          icon={<Globe className="h-4 w-4" />}
          stats={stats.url}
          color="bg-green-500"
        />
      </div>

      {/* Summary Stats */}
      <div className="mt-6 pt-4 border-t border-slate-200">
        <div className="grid grid-cols-4 gap-4 text-center">
          <Stat 
            value={stats.total.queued} 
            label="Total Queued" 
            color="text-blue-600" 
            icon={<Database className="h-3 w-3" />}
          />
          <Stat 
            value={stats.total.processing} 
            label="Total Processing" 
            color="text-amber-600" 
            icon={<Database className="h-3 w-3" />}
          />
          <Stat 
            value={stats.total.completed} 
            label="Total Completed" 
            color="text-green-600" 
            icon={<Database className="h-3 w-3" />}
          />
          <Stat 
            value={stats.total.total} 
            label="Total Items" 
            color="text-slate-700" 
            icon={<Database className="h-3 w-3" />}
          />
        </div>
      </div>
    </section>
  );
}
