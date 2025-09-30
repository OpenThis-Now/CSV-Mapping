import { useRef, useState } from "react";

export default function UploadArea(props: { onFile: (f: File) => void; accept?: string }) {
  const ref = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  return (
    <div
      className={`card border-dashed ${drag ? "border-sky-500" : "border-gray-200"} text-center`}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault(); setDrag(false);
        if (e.dataTransfer.files?.[0]) props.onFile(e.dataTransfer.files[0]);
      }}
    >
      <input ref={ref} type="file" accept={props.accept ?? ".csv"} hidden onChange={(e) => {
        if (e.target.files?.[0]) props.onFile(e.target.files[0]);
      }} />
      <div className="py-10">
        <div className="text-lg font-medium mb-2">Drop CSV here or select file</div>
        <button 
          className="flex items-center gap-1 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded border border-blue-600 hover:border-blue-700 transition-colors mx-auto"
          onClick={() => ref.current?.click()}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          Select file
        </button>
      </div>
    </div>
  );
}
