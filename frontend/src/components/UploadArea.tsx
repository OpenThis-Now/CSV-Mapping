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
        <button className="btn" onClick={() => ref.current?.click()}>Select file</button>
      </div>
    </div>
  );
}
