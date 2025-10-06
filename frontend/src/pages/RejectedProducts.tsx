import React, { useMemo, useRef, useState } from "react";
import {
  Upload,
  Search,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Paperclip,
  Filter,
  PlayCircle,
  RefreshCw,
  Link2
} from "lucide-react";

/***********************************
 * Clickable Canvas Mockup
 * - Header remains the same in your app. This renders only the content below it.
 * - Two tabs: Products (PDF per product row) & Supplier Mapping (CSV upload + Run AI Matching)
 * - No external APIs. Everything mocked in local state so it runs in canvas.
 ***********************************/

/******** Helpers ********/
const toneFor = (status = "") => {
  if (status.includes("missing")) return "amber";
  if (status === "done") return "green";
  return "gray";
};

const filterByQuery = (items = [], q = "") => {
  const s = q.toLowerCase();
  return items.filter((p) => p.name.toLowerCase().includes(s));
};

/******** UI atoms ********/
function Pill({ tone = "gray", children }) {
  const map = {
    gray: "bg-gray-100 text-gray-700",
    amber: "bg-amber-100 text-amber-800",
    green: "bg-emerald-100 text-emerald-800",
    blue: "bg-blue-100 text-blue-800",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${map[tone] || map.gray}`}>
      {children}
    </span>
  );
}

function Dropzone({ onFile, accept = ".pdf", label = "Drag & drop file here or click to select" }) {
  const [isOver, setIsOver] = useState(false);
  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setIsOver(true);
      }}
      onDragLeave={() => setIsOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      className={`flex cursor-pointer items-center gap-3 rounded-xl border-2 border-dashed px-4 py-3 text-sm ${
        isOver ? "border-blue-400 bg-blue-50" : "border-gray-200 hover:bg-gray-50"
      }`}
    >
      <Upload className="h-4 w-4 shrink-0" />
      <span className="truncate">{label}</span>
      <input
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
      />
    </label>
  );
}

/******** Top Actions (shared) ********/
function TopActions({ onExportCsv, onExportZip }) {
  return (
    <div className="sticky top-0 z-10 -mx-4 mb-6 border-b bg-white/80 p-4 backdrop-blur supports-[backdrop-filter]:bg-white/60">
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={onExportCsv} className="rounded-full bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200 hover:bg-emerald-100">
          Export Completed (CSV)
        </button>
        <button onClick={onExportZip} className="rounded-full bg-violet-50 px-3 py-2 text-sm font-medium text-violet-700 ring-1 ring-inset ring-violet-200 hover:bg-violet-100">
          Export Ready for DB import (CSV + ZIP)
        </button>
        <div className="ms-auto flex items-center gap-2 text-xs text-gray-500">
          <Filter className="h-4 w-4" />
          <span>Show:</span>
          <select className="rounded-full border-gray-200 text-xs focus:border-blue-500 focus:ring-blue-500">
            <option>All</option>
            <option>PDF Missing</option>
            <option>CompanyID Missing</option>
            <option>Marked as Done</option>
          </select>
        </div>
      </div>
    </div>
  );
}

/******** Product Row ********/
function ProductRow({ product, index, onSave, onUpload }) {
  const [open, setOpen] = useState(index === 0);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [companyId, setCompanyId] = useState(product.companyId || "");
  const [notes, setNotes] = useState(product.notes || "");
  const fileInputRef = useRef(null);

  const tone = toneFor(product.status);

  const handleUpload = (f) => {
    setFile(f);
    setUploading(true);
    setTimeout(() => {
      setUploading(false);
      onUpload?.(product.id, f);
    }, 800);
  };

  return (
    <div className="rounded-2xl border bg-white shadow-sm">
      <div onClick={() => setOpen(!open)} role="button" className="group flex w-full items-center justify-between gap-4 px-5 py-4 text-left">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <div className="truncate text-base font-semibold">{product.name}</div>
            <Pill tone={tone}>{product.status_label}</Pill>
            {file && <Pill tone="green">PDF Selected</Pill>}
            {product.pdf && <Pill tone="green"><Paperclip className="h-3.5 w-3.5"/> Linked</Pill>}
          </div>
          <div className="mt-1 line-clamp-1 text-xs text-gray-500">{product.reason}</div>
        </div>
        <div className="flex items-center gap-1">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            className="sr-only"
            onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
          />
          <button
            onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
            className="rounded-full p-2 md:opacity-0 md:group-hover:opacity-100 hover:bg-gray-100 focus:opacity-100 focus:outline-none"
            title="Upload PDF"
            aria-label="Upload PDF"
          >
            {uploading ? <Loader2 className="h-4 w-4 animate-spin text-gray-600"/> : <Upload className="h-4 w-4 text-gray-600"/>}
          </button>
          {open ? <ChevronUp className="h-5 w-5 text-gray-400"/> : <ChevronDown className="h-5 w-5 text-gray-400"/>}
        </div>
      </div>

      {open && (
        <div className="grid gap-5 border-t px-5 py-5 md:grid-cols-3">
          <div className="md:col-span-1">
            <div className="text-xs font-medium text-gray-700">Upload PDF</div>
            <div className="mt-2">
              <Dropzone onFile={handleUpload} />
              {file && (
                <div className="mt-2 inline-flex items-center gap-2 rounded-full bg-gray-100 px-3 py-1 text-xs">
                  <Paperclip className="h-3.5 w-3.5"/> {file.name}
                </div>
              )}
            </div>
          </div>

          <div className="space-y-3 md:col-span-1">
            <div>
              <label className="text-xs font-medium text-gray-700">Company ID</label>
              <div className="mt-1 flex gap-2">
                <input value={companyId} onChange={(e) => setCompanyId(e.target.value)} placeholder="Enter Company ID" className="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200"/>
                <button className="inline-flex items-center gap-1 rounded-xl border border-gray-200 px-3 text-xs hover:bg-gray-50"><Search className="h-4 w-4"/> Auto-match</button>
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-700">Status</label>
              <select defaultValue={product.status} className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200">
                <option value="pdf_missing">PDF Missing</option>
                <option value="company_missing">CompanyID Missing</option>
                <option value="pdf_company_missing">PDF & CompanyID Missing</option>
                <option value="done">Done</option>
              </select>
            </div>
          </div>

          <div className="space-y-3 md:col-span-1">
            <div>
              <label className="text-xs font-medium text-gray-700">Notes</label>
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={5} placeholder="Add any notes here" className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200"/>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={() => onSave?.({ id: product.id, pdf: file, companyId, notes })} className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
                <CheckCircle2 className="h-4 w-4"/> Save
              </button>
              <button onClick={() => onSave?.({ id: product.id, pdf: file, companyId, notes })} className="inline-flex items-center gap-2 rounded-xl border border-gray-200 px-4 py-2 text-sm hover:bg-gray-50">
                Save & Next
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/******** Products Tab ********/
function ProductsTab() {
  const [query, setQuery] = useState("");
  const [uploadingZip, setUploadingZip] = useState(false);
  const [items, setItems] = useState(() => [
    { id: 1, name: "Mill White", status: "pdf_company_missing", status_label: "PDF & CompanyID Missing", reason: "Incomplete data – Supplier missing", pdf: null },
    { id: 2, name: "Ultradeep Base", status: "pdf_company_missing", status_label: "PDF & CompanyID Missing", reason: "Incomplete data – Supplier missing", pdf: null },
    { id: 3, name: "Pro Seal 200", status: "pdf_missing", status_label: "PDF Missing", reason: "Only CompanyID available", pdf: null },
  ]);

  const filtered = useMemo(() => filterByQuery(items, query), [items, query]);

  const onSave = (payload) => {
    // Mock save
    setItems((prev) => prev.map((p) => (p.id === payload.id ? { ...p, pdf: payload.pdf } : p)));
    alert(`Saved: ${payload.id}`);
  };

  return (
    <>
      <TopActions onExportCsv={() => alert("Export CSV")} onExportZip={() => alert("Export ZIP")}/>

      {/* Bulk ZIP upload */}
      <div className="bg-white rounded-xl border p-4 mb-6">
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <h3 className="font-semibold mb-2">Bulk PDF Upload</h3>
            <p className="text-sm text-gray-600 mb-3">Upload a ZIP with PDFs. The system will try to auto-assign based on filename.</p>
            <input type="file" accept=".zip" className="text-sm" onChange={(e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              setUploadingZip(true);
              setTimeout(() => setUploadingZip(false), 1000);
            }}/>
          </div>
          {uploadingZip && <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"/>}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2 rounded-xl border bg-white px-3 py-2 shadow-sm">
          <Search className="h-4 w-4 text-gray-400"/>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search products…" className="w-64 text-sm outline-none"/>
        </div>
        <div className="text-sm text-gray-500">{filtered.length} products</div>
      </div>

      <div className="grid gap-4">
        {filtered.map((p, idx) => (
          <ProductRow key={p.id} product={p} index={idx} onSave={onSave} onUpload={(id, f) => onSave({ id, pdf: f })}/>
        ))}
      </div>
    </>
  );
}

/******** Supplier Mapping Tab ********/
function SupplierMappingTab() {
  const [csv, setCsv] = useState(null);
  const [running, setRunning] = useState(false);
  const [summary, setSummary] = useState({ unique: 1, totalProducts: 9, csvSuppliers: 41747, unmatched: ["MAPEI INC. (Canada)"] });

  const run = () => {
    setRunning(true);
    setTimeout(() => setRunning(false), 1000);
  };

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold">Upload Suppliers CSV</h3>
            <p className="mt-1 text-sm text-gray-500">Upload a CSV with supplier data. Required: Supplier name, CompanyID, Country. Optional: Total.</p>
          </div>
          <button onClick={run} disabled={!csv || running} className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-blue-300">
            {running ? <Loader2 className="h-4 w-4 animate-spin"/> : <PlayCircle className="h-4 w-4"/>} Run AI Matching
          </button>
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <div className="md:col-span-2">
            <Dropzone accept=".csv" onFile={setCsv} label="Drag & drop CSV here or click to select"/>
            {csv && <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-gray-100 px-3 py-1 text-xs"><Paperclip className="h-3.5 w-3.5"/>{csv.name}</div>}
            <details className="mt-4">
              <summary className="cursor-pointer text-sm font-medium text-gray-700">CSV Format</summary>
              <ul className="mt-2 list-disc space-y-1 ps-5 text-sm text-gray-600">
                <li><b>Supplier name</b> – supplier/company name</li>
                <li><b>CompanyID</b> – company identifier</li>
                <li><b>Country</b> – country/market code</li>
                <li><b>Total</b> – product count (optional)</li>
              </ul>
            </details>
          </div>
          <div className="space-y-3">
            <div className="rounded-2xl border bg-white p-5 shadow-sm"><div className="text-2xl font-semibold">{summary.unique}</div><div className="text-sm text-gray-500">Unique suppliers</div></div>
            <div className="rounded-2xl border bg-white p-5 shadow-sm"><div className="text-2xl font-semibold">{summary.totalProducts}</div><div className="text-sm text-gray-500">Total products</div></div>
            <div className="rounded-2xl border bg-white p-5 shadow-sm"><div className="text-2xl font-semibold">{summary.csvSuppliers}</div><div className="text-sm text-gray-500">CSV suppliers</div></div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold">Suppliers without matches</h3>
          <button className="inline-flex items-center gap-2 rounded-xl border border-gray-200 px-3 py-1.5 text-xs hover:bg-gray-50"><RefreshCw className="h-3.5 w-3.5"/> Try again</button>
        </div>
        <ul className="mt-3 divide-y">
          {summary.unmatched.map((u) => (
            <li key={u} className="flex items-center justify-between py-3 text-sm">
              <div>
                <div className="font-medium">{u}</div>
                <div className="text-xs text-gray-500">Country: Canada • Products: 1</div>
              </div>
              <button className="rounded-full bg-gray-100 px-3 py-1 text-xs">View</button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/******** Main ********/
export default function RejectedProductsMock() {
  const [tab, setTab] = useState("products");

  return (
    <div className="mx-auto max-w-6xl px-4 pb-20">
      <div className="mb-5 mt-2 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Rejected Products</h1>
        <div className="rounded-xl bg-gray-100 px-3 py-1 text-xs text-gray-600">Project: Australian SDSs</div>
      </div>

      <div className="mb-6 inline-flex rounded-xl border bg-white p-1 shadow-sm">
        <button onClick={() => setTab("products")} className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === "products" ? "bg-gray-900 text-white" : "text-gray-700 hover:bg-gray-50"}`}>Products</button>
        <button onClick={() => setTab("mapping")} className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === "mapping" ? "bg-gray-900 text-white" : "text-gray-700 hover:bg-gray-50"}`}>Supplier Mapping</button>
      </div>

      {tab === "products" ? <ProductsTab/> : <SupplierMappingTab/>}
    </div>
  );
}