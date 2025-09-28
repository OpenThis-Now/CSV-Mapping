import api from "@/lib/api";
import { useState } from "react";

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
      id: "approved",
      title: "Approved matches",
      description: "Exports only matches that are approved",
      icon: "✅",
      color: "bg-green-50 border-green-200"
    },
    {
      id: "all",
      title: "Complete results",
      description: "Exports all matches with all statuses (approved, not_approved, sent_to_ai, auto_approved)",
      icon: "📊",
      color: "bg-blue-50 border-blue-200"
    },
    {
      id: "rejected",
      title: "Rejected matches",
      description: "Exports matches that are marked as not_approved",
      icon: "❌",
      color: "bg-red-50 border-red-200"
    },
    {
      id: "ai_pending",
      title: "AI pending",
      description: "Exports matches that are sent to AI (sent_to_ai)",
      icon: "🤖",
      color: "bg-purple-50 border-purple-200"
    }
  ];

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl shadow p-6">
        <h1 className="text-3xl font-bold mb-6">📤 Export options</h1>
        <p className="text-gray-600 mb-6">
          Choose which type of data you want to export from your project.
        </p>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {exportOptions.map((option) => (
            <div key={option.id} className={`border-2 rounded-xl p-4 ${option.color}`}>
              <div className="flex items-start gap-3">
                <div className="text-2xl">{option.icon}</div>
                <div className="flex-1">
                  <h3 className="font-semibold text-lg mb-2">{option.title}</h3>
                  <p className="text-sm text-gray-600 mb-3">{option.description}</p>
                  <button
                    onClick={() => exportCsv(option.id)}
                    disabled={loading === option.id}
                    className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {loading === option.id ? (
                      <span className="flex items-center gap-2">
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                        Exporting...
                      </span>
                    ) : (
                      "📥 Download CSV"
                    )}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mt-6">
          <h3 className="font-semibold text-yellow-900 mb-2">💡 Tips:</h3>
          <ul className="text-sm text-yellow-800 space-y-1">
            <li>• <strong>Approved matches</strong> - Use for final results</li>
            <li>• <strong>Complete results</strong> - Use for complete overview of all matches</li>
            <li>• <strong>Rejected matches</strong> - Use to see what didn't match</li>
            <li>• <strong>AI pending</strong> - Use to see products waiting for AI analysis</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
