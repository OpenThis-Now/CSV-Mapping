import { useState } from 'react';
import { Download } from 'lucide-react';

export default function InfoPage() {
  const [tab, setTab] = useState("input");

  const inputRequired = [
    "Product_name - Product name (required)",
    "Supplier_name - Supplier name (required)", 
    "Article_number - Article number/SKU (required)",
    "Market - Market/Region (required)",
    "Language - Language (required)",
  ];
  const inputOptional = [
    "Location_ID - Location ID (optional)",
    "Product_ID - Product ID (optional)",
    "Description - Description (optional)",
    "SDS-URL - URL to PDF safety data sheet (optional)",
  ];
  const inputTemplate = `Product_name;Supplier_name;Article_number;Market;Language;Location_ID;Product_ID;Description;SDS-URL
THINNER 215;Carboline;05570910001D;Canada;English;LOC001;PROD001;Industrial paint thinner;https://example.com/sds/thinner215.pdf
MAPEFLOOR FILLER;MAPEI INC.;245633;Canada;English;LOC002;PROD002;Floor filler compound;https://example.com/sds/mapefloor.pdf
BAR-RUST 235 BLACK PART A;AkzoNobel;HB9903;Sweden;Swedish;LOC003;PROD003;Rust protection paint;https://example.com/sds/bar-rust.pdf`;

  const dbRequired = [
    "Product_name - Product name (required)",
    "Supplier_name - Supplier name (required)",
    "Article_number - Article number/SKU (required)",
    "Market - Market/Region (required)",
    "Language - Language (required)",
  ];
  const dbOptional = [
    "Unique_ID - Company ID (optional)",
    "MSDSkey - Safety data sheet key (optional)",
    "Revision_date - Revision date (optional)",
    "Expire_date - Expiration date (optional)",
    "Description - Description (optional)",
    "File_hash - SHA-512 hash of original file (optional)",
  ];
  const dbTemplate = `Product_name;Supplier_name;Article_number;Market;Language;Unique_ID;MSDSkey;Revision_date;Expire_date;Description;File_hash
THINNER 215;Carboline;05570910001D;Canada;English;12345;26139007;2024-01-15;2025-12-31;Industrial paint thinner;a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
MAPEFLOOR FILLER NA;MAPEI INC.;245633;Canada;English;12347;26146274;2024-02-01;2026-01-31;Floor filler compound;b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890
BAR-RUST 235 BLACK PART A;AkzoNobel;HB9903;Sweden;Swedish;12348;26146498;2024-01-20;2025-06-30;Rust protection paint;c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef`;

  const tips = [
    "Use semicolon (;) as separator, not comma (,)",
    "Save as UTF-8 for Nordic characters (å, ä, ö, æ, ø, þ, ð)",
    "First row should contain column names exactly as shown above",
    "Empty cells are allowed for optional fields",
    "Date format: YYYY-MM-DD (e.g. 2024-01-15)",
    "SDS-URL: Must be direct links to PDF files (http:// or https://)",
    "Market values: Use 'Canada', 'Sweden', 'Norway', 'Denmark', etc.",
    "Language values: Use 'English', 'Swedish', 'Norwegian', 'Danish', etc.",
    "Column names are case-sensitive - use exact names shown above",
    "AI Enhancement: Works best with well-formatted SDS documents",
    "File_hash: SHA-512 hash of original file (128 hex characters) - optional for tracking",
  ];

  const onDownload = (csv: string, filename: string) => {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Helper functions
  function cx(...classes: Array<string | false | undefined>) {
    return classes.filter(Boolean).join(" ");
  }

  function PrimaryButton({ onClick, ariaLabel, children, className = "", disabled = false }: any) {
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
        <Download className="h-4 w-4" aria-hidden />
        {children}
      </button>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      <main className="mx-auto max-w-5xl px-4 py-8 md:py-10">
        <section className="mb-4 md:mb-6">
          <h1 className="text-[28px] md:text-[32px] font-bold tracking-[-0.01em] text-slate-900">Information & CSV Templates</h1>
        </section>

        <div className="mb-4" role="tablist" aria-label="CSV tabs">
          <div className="inline-flex gap-1 rounded-2xl border border-slate-200 bg-slate-50 p-1">
            {[
              { key: "input", label: "Input CSV" },
              { key: "database", label: "Database CSV" },
            ].map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={tab === t.key}
                className={cx(
                  "rounded-xl px-3 py-1.5 text-sm font-medium",
                  tab === t.key ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200" : "text-slate-700 hover:text-slate-900"
                )}
                onClick={() => setTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {tab === "input" ? (
          <>
            <section className="rounded-2xl border border-blue-200 bg-blue-50 p-5 md:p-6 shadow-sm">
              <h2 className="text-base md:text-lg font-semibold text-slate-900">Input CSV Files</h2>
              <p className="mt-1 text-slate-700">These fields are used to import customer data that will be matched against the database.</p>
              <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-2">
                <div>
                  <p className="text-sm font-semibold text-slate-900">Required fields</p>
                  <ul className="mt-2 list-disc pl-5 space-y-1 text-sm text-slate-700">
                    {inputRequired.map((x) => (
                      <li key={x}><span className="font-mono text-slate-800">{x.split(" - ")[0]}</span> - {x.split(" - ")[1]}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">Optional fields</p>
                  <ul className="mt-2 list-disc pl-5 space-y-1 text-sm text-slate-700">
                    {inputOptional.map((x) => (
                      <li key={x}><span className="font-mono text-slate-800">{x.split(" - ")[0]}</span> - {x.split(" - ")[1]}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>

            <section className="mt-6" aria-label="Input CSV Template">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">Input CSV Template</h3>
                <PrimaryButton ariaLabel="Download Input Template" onClick={() => onDownload(inputTemplate, 'input_template.csv')}>Download Template</PrimaryButton>
              </div>
              <div className="mt-3 rounded-xl border border-slate-200 bg-white shadow-sm">
                <pre className="overflow-x-auto whitespace-pre-wrap p-4 text-sm text-slate-800 font-mono">{inputTemplate}</pre>
              </div>
            </section>

            <section className="mt-6 rounded-2xl border border-slate-200 bg-slate-50 p-5 md:p-6 shadow-sm">
              <h3 className="text-base font-semibold text-slate-900">AI‑powered SDS‑URL enhancement</h3>
              <p className="mt-1 text-slate-700">When SDS‑URL links are included, the system can extract and enhance product information using AI.</p>
              <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-3">
                <div>
                  <p className="text-sm font-semibold text-slate-900">What gets enhanced</p>
                  <ul className="mt-2 list-disc pl-5 space-y-1 text-sm text-slate-700">
                    {["Product_name - From PDF content","Supplier_name - From PDF content","Article_number - From PDF content","Market - Detected market/region","Language - Detected document language"].map((x)=> (
                      <li key={x}><span className="font-mono text-slate-800">{x.split(" - ")[0]}</span> - {x.split(" - ")[1]}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">What stays the same</p>
                  <ul className="mt-2 list-disc pl-5 space-y-1 text-sm text-slate-700">
                    {["All unique IDs and identifiers","Custom fields and descriptions","Existing data not found in PDF","Original CSV structure"].map((x)=> (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">How to use</p>
                  <ul className="mt-2 list-disc pl-5 space-y-1 text-sm text-slate-700">
                    {["Add SDS-URL column with PDF links to your CSV","Upload the CSV file as usual","Click \"Re-write with URL link data\" button","AI processes PDFs and enhances your data","Download the enhanced CSV with updated information"].map((x)=> (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>

            <section className="mt-6" aria-label="Important tips">
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 md:p-5 shadow-sm">
                <h4 className="text-sm font-semibold text-slate-900">Important tips</h4>
                <ul className="mt-2 list-disc pl-5 space-y-1 text-sm text-slate-800">
                  {tips.map((t) => (<li key={t}>{t}</li>))}
                </ul>
              </div>
            </section>
          </>
        ) : (
          <>
            <section className="rounded-2xl border border-green-200 bg-green-50 p-5 md:p-6 shadow-sm">
              <h2 className="text-base md:text-lg font-semibold text-slate-900">Database CSV Files</h2>
              <p className="mt-1 text-slate-700">These fields are used to create product databases that customer data is matched against.</p>
              <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-2">
                <div>
                  <p className="text-sm font-semibold text-slate-900">Required fields</p>
                  <ul className="mt-2 list-disc pl-5 space-y-1 text-sm text-slate-700">
                    {dbRequired.map((x) => (
                      <li key={x}><span className="font-mono text-slate-800">{x.split(" - ")[0]}</span> - {x.split(" - ")[1]}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">Optional fields</p>
                  <ul className="mt-2 list-disc pl-5 space-y-1 text-sm text-slate-700">
                    {dbOptional.map((x) => (
                      <li key={x}><span className="font-mono text-slate-800">{x.split(" - ")[0]}</span> - {x.split(" - ")[1]}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>

            <section className="mt-6" aria-label="Database CSV Template">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">Database CSV Template</h3>
                <PrimaryButton ariaLabel="Download Database Template" onClick={() => onDownload(dbTemplate, 'database_template.csv')}>Download Template</PrimaryButton>
              </div>
              <div className="mt-3 rounded-xl border border-slate-200 bg-white shadow-sm">
                <pre className="overflow-x-auto whitespace-pre-wrap p-4 text-sm text-slate-800 font-mono">{dbTemplate}</pre>
              </div>
            </section>

            <section className="mt-6" aria-label="Important tips">
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 md:p-5 shadow-sm">
                <h4 className="text-sm font-semibold text-slate-900">Important tips</h4>
                <ul className="mt-2 list-disc pl-5 space-y-1 text-sm text-slate-800">
                  {tips.map((t) => (<li key={t}>{t}</li>))}
                </ul>
              </div>
            </section>

            <section className="mt-6" aria-label="Troubleshooting">
              <div className="rounded-2xl border border-red-200 bg-red-50 p-4 md:p-5 shadow-sm">
                <h4 className="text-sm font-semibold text-slate-900">Troubleshooting: "Not on market & language" errors</h4>
                <div className="mt-2 text-sm text-slate-800">
                  <p className="mb-2">If you see "Not on market & language" errors, check these common issues:</p>
                  <ul className="list-disc pl-5 space-y-1">
                    <li><strong>Column names:</strong> Must match exactly (case-sensitive): Product_name, Supplier_name, Article_number, Market, Language</li>
                    <li><strong>Market values:</strong> Use exact values like "Canada", "Sweden", "Norway" (not "CA", "SE", "NO")</li>
                    <li><strong>Language values:</strong> Use exact values like "English", "Swedish", "Norwegian" (not "EN", "SV", "NO")</li>
                    <li><strong>Mixed databases:</strong> If your database contains multiple markets, ensure each customer row has the correct market/language</li>
                    <li><strong>UTF-8 encoding:</strong> Save files as UTF-8 to avoid character encoding issues</li>
                    <li><strong>Separator:</strong> Use semicolon (;) not comma (,) as separator</li>
                  </ul>
                </div>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
