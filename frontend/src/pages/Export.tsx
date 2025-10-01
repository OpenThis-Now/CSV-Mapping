import api from "@/lib/api";
import { useState } from "react";
import { CheckCircle2, XCircle, Clock, Layers, Download } from "lucide-react";

export default function ExportPage({ projectId }: { projectId: number }) {
  const [loading, setLoading] = useState<string | null>(null);

  const exportCsv = async (type: string) => {
    setLoading(type);
    try {
      const res = await api.get(`/projects/${projectId}/export.csv?type=${type}`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; 
      a.download = `project_${projectId}_${type}_export.csv`; 
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Export failed:", error);
      alert("Export failed. Please try again.");
    } finally {
      setLoading(null);
    }
  };

  const exportOptions = [
    {
      key: "approved",
      title: "Approved matches",
      desc: "Exports only matches that are approved",
      badge: { label: "Approved", tone: "green" },
      toneBg: "bg-green-50",
      iconBg: "bg-green-100",
      iconColor: "text-green-700",
      Icon: CheckCircle2,
    },
    {
      key: "all",
      title: "Complete results",
      desc: "Exports all matches with all statuses",
      badge: { label: "Complete", tone: "slate" },
      toneBg: "bg-slate-50",
      iconBg: "bg-slate-100",
      iconColor: "text-slate-700",
      Icon: Layers,
    },
    {
      key: "rejected",
      title: "Rejected matches",
      desc: "Exports matches marked as not_approved",
      badge: { label: "Rejected", tone: "rose" },
      toneBg: "bg-rose-50",
      iconBg: "bg-rose-100",
      iconColor: "text-rose-700",
      Icon: XCircle,
    },
    {
      key: "ai_pending",
      title: "AI pending",
      desc: "Exports matches sent_to_ai",
      badge: { label: "AI pending", tone: "violet" },
      toneBg: "bg-violet-50",
      iconBg: "bg-violet-100",
      iconColor: "text-violet-700",
      Icon: Clock,
    },
  ];

  // Helper functions
  function cx(...classes: Array<string | false | undefined>) {
    return classes.filter(Boolean).join(" ");
  }

  function Badge({ label, tone = "slate" }: { label: string; tone?: "green" | "rose" | "slate" | "violet" }) {
    const toneMap: Record<string, string> = {
      green: "bg-green-50 text-green-700 ring-green-200",
      rose: "bg-rose-50 text-rose-700 ring-rose-200",
      slate: "bg-slate-50 text-slate-700 ring-slate-200",
      violet: "bg-violet-50 text-violet-700 ring-violet-200",
    };
    return (
      <span className={cx("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ring-1", toneMap[tone])}>
        {label}
      </span>
    );
  }

  function IconChip({ Icon, bg, color, title }: { Icon: any; bg: string; color: string; title: string }) {
    return (
      <div aria-hidden className={cx("flex h-10 w-10 items-center justify-center rounded-xl", bg, color)} title={title}>
        <Icon className="h-5 w-5" />
      </div>
    );
  }

  function PrimaryButton({ onClick, ariaLabel, children, className = "", disabled = false, isLoading = false }: any) {
    return (
      <button
        type="button"
        onClick={onClick}
        aria-label={ariaLabel}
        disabled={disabled}
        className={cx(
          "inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-white shadow-sm",
          "hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          className
        )}
      >
        {isLoading ? (
          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
        ) : (
          <Download className="h-4 w-4" aria-hidden />
        )}
        {children}
      </button>
    );
  }

  function Card({ item }: { item: any }) {
    const { Icon, title, toneBg, iconBg, iconColor, key, badge } = item;
    return (
      <section className="group rounded-2xl border border-slate-200 bg-white shadow-sm focus-within:ring-2 focus-within:ring-blue-600">
        <div className={cx("flex items-center gap-4 p-5 md:p-6 rounded-2xl", toneBg)}>
          <IconChip Icon={Icon} bg={iconBg} color={iconColor} title={title} />
          <div className="flex min-w-0 flex-1 items-center justify-between">
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-slate-900 truncate">{title}</h3>
              <div className="mt-2"><Badge label={badge.label} tone={badge.tone as any} /></div>
            </div>
            <div className="ml-4 shrink-0">
              <PrimaryButton 
                ariaLabel={`Download CSV for ${title}`} 
                onClick={() => exportCsv(key)}
                disabled={loading === key}
                isLoading={loading === key}
              >
                {loading === key ? "Exporting..." : "Download CSV"}
              </PrimaryButton>
            </div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      <main className="mx-auto max-w-7xl px-4 py-8 md:py-10">
        {/* Snygg, ren sidtitel utan emoji */}
        <section aria-labelledby="page-title" className="mb-4 md:mb-6">
          <h1 id="page-title" className="text-[28px] md:text-[32px] font-bold tracking-[-0.01em] text-slate-900">Export options</h1>
          <p className="mt-1 text-sm md:text-base text-slate-600">Select a dataset to export as CSV.</p>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 md:p-6" aria-label="Export grid">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {exportOptions.map((item) => (
              <Card key={item.key} item={item} />
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
