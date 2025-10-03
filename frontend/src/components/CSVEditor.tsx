import React, { useMemo, useState } from "react";

type CSVRow = Record<string, string>;

interface CSVEditorProps {
  file: {
    id: number;
    filename: string;
    row_count: number;
    columns_map_json: Record<string, string>;
  };
  csvData: CSVRow[];
  onSave: (rows: CSVRow[]) => void;
  onCancel: () => void;
}

function TrashIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

const baseBtn = "inline-flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50";
const btnGray = `${baseBtn} border-gray-200 bg-white text-gray-700 hover:bg-gray-50 focus:ring-gray-200`;
const btnGreen = `${baseBtn} border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700 focus:ring-emerald-600`;
const btnGhostDanger = `${baseBtn} border-transparent bg-transparent text-gray-600 hover:text-red-700 hover:bg-red-50`;

export default function CSVEditor({ file, csvData, onSave, onCancel }: CSVEditorProps) {
  const [rows, setRows] = useState<CSVRow[]>(() => csvData.map(r => ({...r})));

  const columns = useMemo(() => {
    if (rows.length === 0) return [];
    const set = new Set(Object.keys(rows[0] || {}));
    rows.forEach(r => Object.keys(r).forEach(k => set.add(k)));
    return Array.from(set);
  }, [rows]);

  function setCell(i: number, key: string, val: string) {
    setRows(prev => {
      const next = [...prev];
      next[i] = { ...next[i], [key]: val };
      return next;
    });
  }

  function addRow() {
    const blank: CSVRow = {};
    columns.forEach(k => blank[k] = "");
    setRows(prev => [blank, ...prev]);
  }

  function deleteRow(i: number) {
    setRows(prev => prev.filter((_, idx) => idx !== i));
  }

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-gray-200 bg-white">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 bg-gray-50 p-3">
        <div className="text-sm text-gray-600">{rows.length} rows</div>
        <div className="flex items-center gap-2">
          <button className={btnGray} onClick={addRow}>Add Row</button>
          <button className={btnGreen} onClick={() => onSave(rows)}>Save Changes</button>
          <button className={btnGray} onClick={onCancel}>Cancel</button>
        </div>
      </div>

      {/* Table */}
      <div className="w-full overflow-x-auto">
        <table className="min-w-full border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              {columns.map(col => (
                <th key={col} className="sticky top-0 z-10 border-b border-gray-200 bg-white p-2 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                  {col}
                </th>
              ))}
              <th className="sticky top-0 z-10 border-b border-gray-200 bg-white p-2 text-right text-[11px] font-semibold uppercase tracking-wide text-gray-500">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b last:border-b-0">
                {columns.map((key) => (
                  <td key={key} className="p-2 align-top">
                    <input
                      className="w-full rounded-md border border-gray-200 bg-white px-2 py-1 text-sm text-gray-800 focus:border-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-200"
                      value={row[key] ?? ""}
                      onChange={(e) => setCell(i, key, e.target.value)}
                      placeholder={key}
                    />
                  </td>
                ))}
                <td className="p-2 text-right align-top">
                  <button className={`${btnGhostDanger} group`} onClick={() => deleteRow(i)}>
                    <TrashIcon className="mr-1.5 h-4 w-4 hidden group-hover:inline-block" />
                    <span>Delete</span>
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={columns.length + 1} className="p-6 text-center text-gray-500">No rows yet. Click <span className="font-medium">Add Row</span> to start.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
