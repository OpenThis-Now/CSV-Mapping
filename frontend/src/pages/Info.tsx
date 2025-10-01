import { useState } from 'react';

export default function InfoPage() {
  const [activeTab, setActiveTab] = useState<'input' | 'database'>('input');

  const inputTemplate = `Product_name;Supplier_name;Article_number;Market;Language;Description;SDS-URL
THINNER 215;Carboline;05570910001D;Canada;English;Industrial paint thinner;https://example.com/sds/thinner215.pdf
MAPEFLOOR FILLER;MAPEI INC.;245633;Canada;English;Floor filler compound;https://example.com/sds/mapefloor.pdf
BAR-RUST 235 BLACK;AkzoNobel;HB9903;Canada;English;Rust protection paint;https://example.com/sds/bar-rust.pdf`;

  const databaseTemplate = `Product_name;Supplier_name;Article_number;Unique_ID;Location_ID;Market;Language;MSDSkey;Revision_date;Expire_date
THINNER 215;Carboline;05570910001D;12345;12345;Canada;English;26139007;2024-01-15;2025-12-31
MAPEFLOOR FILLER NA;MAPEI INC.;245633;12347;12345;Canada;English;26146274;2024-02-01;2026-01-31
BAR-RUST 235 BLACK PART A;AkzoNobel;HB9903;12348;12345;Canada;English;26146498;2024-01-20;2025-06-30`;

  const downloadCSV = (content: string, filename: string) => {
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl shadow p-6">
        <h1 className="text-3xl font-bold mb-6">📋 Information & CSV Templates</h1>
        
        {/* Tab Navigation */}
        <div className="flex space-x-1 bg-gray-100 p-1 rounded-lg mb-6">
          <button
            onClick={() => setActiveTab('input')}
            className={`px-4 py-2 rounded-md font-medium transition-colors ${
              activeTab === 'input'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            📥 Input CSV
          </button>
          <button
            onClick={() => setActiveTab('database')}
            className={`px-4 py-2 rounded-md font-medium transition-colors ${
              activeTab === 'database'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            🗄️ Database CSV
          </button>
        </div>

        {/* Input CSV Tab */}
        {activeTab === 'input' && (
          <div className="space-y-6">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <h2 className="text-xl font-semibold text-blue-900 mb-3">📥 Input CSV Files</h2>
              <p className="text-blue-800 mb-4">
                These fields are used to import customer data that will be matched against the database.
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                  <h3 className="font-semibold text-blue-900 mb-2">✅ Required fields:</h3>
                  <ul className="text-sm text-blue-800 space-y-1">
                    <li>• <code>Product_name</code> - Product name</li>
                    <li>• <code>Supplier_name</code> - Supplier name</li>
                    <li>• <code>Article_number</code> - Art.no</li>
                  </ul>
                </div>
                <div>
                  <h3 className="font-semibold text-blue-900 mb-2">🔧 Optional fields:</h3>
                  <ul className="text-sm text-blue-800 space-y-1">
                    <li>• <code>Market</code> - Market/Region</li>
                    <li>• <code>Language</code> - Language</li>
                    <li>• <code>Description</code> - Description</li>
                    <li>• <code>SDS-URL</code> - URL to PDF safety data sheet</li>
                  </ul>
                </div>
              </div>
            </div>

            <div className="bg-gray-50 rounded-lg p-4">
              <div className="flex justify-between items-center mb-3">
                <h3 className="font-semibold">Input CSV Template</h3>
                <button
                  onClick={() => downloadCSV(inputTemplate, 'input_template.csv')}
                  className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
                >
                  📥 Download Template
                </button>
              </div>
              <pre className="bg-white border rounded p-3 text-sm overflow-x-auto">
                <code>{inputTemplate}</code>
              </pre>
            </div>

            {/* SDS-URL Enhancement Section */}
            <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
              <h2 className="text-xl font-semibold text-purple-900 mb-3">🤖 AI-Powered SDS-URL Enhancement</h2>
              <p className="text-purple-800 mb-4">
                When you include SDS-URL links in your CSV, the system can automatically extract and enhance product information using AI.
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                  <h3 className="font-semibold text-purple-900 mb-2">✨ What gets enhanced:</h3>
                  <ul className="text-sm text-purple-800 space-y-1">
                    <li>• <code>Product_name</code> - From PDF content</li>
                    <li>• <code>Supplier_name</code> - From PDF content</li>
                    <li>• <code>Article_number</code> - From PDF content</li>
                    <li>• <code>Market</code> - Detected market/region</li>
                    <li>• <code>Language</code> - Detected document language</li>
                  </ul>
                </div>
                <div>
                  <h3 className="font-semibold text-purple-900 mb-2">🔒 What stays the same:</h3>
                  <ul className="text-sm text-purple-800 space-y-1">
                    <li>• All unique IDs and identifiers</li>
                    <li>• Custom fields and descriptions</li>
                    <li>• Existing data not found in PDF</li>
                    <li>• Original CSV structure</li>
                  </ul>
                </div>
              </div>

              <div className="bg-white border border-purple-200 rounded p-3 mb-3">
                <h4 className="font-semibold text-purple-900 mb-2">🚀 How to use:</h4>
                <ol className="text-sm text-purple-800 space-y-1 list-decimal list-inside">
                  <li>Add SDS-URL column with PDF links to your CSV</li>
                  <li>Upload the CSV file as usual</li>
                  <li>Click "Re-write with URL link data" button</li>
                  <li>AI processes PDFs and enhances your data</li>
                  <li>Download the enhanced CSV with updated information</li>
                </ol>
              </div>
            </div>
          </div>
        )}

        {/* Database CSV Tab */}
        {activeTab === 'database' && (
          <div className="space-y-6">
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <h2 className="text-xl font-semibold text-green-900 mb-3">🗄️ Database CSV Files</h2>
              <p className="text-green-800 mb-4">
                These fields are used to create product databases that customer data is matched against.
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                  <h3 className="font-semibold text-green-900 mb-2">✅ Required fields:</h3>
                  <ul className="text-sm text-green-800 space-y-1">
                    <li>• <code>Product_name</code> - Product name</li>
                    <li>• <code>Supplier_name</code> - Supplier name</li>
                    <li>• <code>Article_number</code> - Art.no</li>
                    <li>• <code>Market</code> - Market/Region</li>
                    <li>• <code>Language</code> - Language</li>
                  </ul>
                </div>
                <div>
                  <h3 className="font-semibold text-green-900 mb-2">🔧 Optional fields:</h3>
                  <ul className="text-sm text-green-800 space-y-1">
                    <li>• <code>Unique_ID</code> - Unique identifier</li>
                    <li>• <code>Location_ID</code> - Location ID</li>
                    <li>• <code>MSDSkey</code> - Safety data sheet</li>
                    <li>• <code>Revision_date</code> - Revision date</li>
                    <li>• <code>Expire_date</code> - Expiration date</li>
                    <li>• <code>Description</code> - Description</li>
                  </ul>
                </div>
              </div>
            </div>

            <div className="bg-gray-50 rounded-lg p-4">
              <div className="flex justify-between items-center mb-3">
                <h3 className="font-semibold">Database CSV Template</h3>
                <button
                  onClick={() => downloadCSV(databaseTemplate, 'database_template.csv')}
                  className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 transition-colors"
                >
                  📥 Download Template
                </button>
              </div>
              <pre className="bg-white border rounded p-3 text-sm overflow-x-auto">
                <code>{databaseTemplate}</code>
              </pre>
            </div>
          </div>
        )}

        {/* General Information */}
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mt-6">
          <h3 className="font-semibold text-yellow-900 mb-2">⚠️ Important tips:</h3>
          <ul className="text-sm text-yellow-800 space-y-1">
            <li>• <strong>Use semicolon (;)</strong> as separator, not comma (,)</li>
            <li>• <strong>Save as UTF-8</strong> for Nordic characters (å, ä, ö, æ, ø, þ, ð)</li>
            <li>• <strong>First row</strong> should contain column names</li>
            <li>• <strong>Empty cells</strong> are allowed for optional fields</li>
            <li>• <strong>Date format:</strong> YYYY-MM-DD (e.g. 2024-01-15)</li>
            <li>• <strong>SDS-URL:</strong> Must be direct links to PDF files (http:// or https://)</li>
            <li>• <strong>AI Enhancement:</strong> Works best with well-formatted SDS documents</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
