import { useRef, useState } from "react";

export default function UploadArea(props: { 
  onFile?: (f: File) => void; 
  onFiles?: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const handleFiles = (files: FileList) => {
    if (props.multiple && props.onFiles) {
      const fileArray = Array.from(files);
      props.onFiles(fileArray);
    } else if (props.onFile && files[0]) {
      props.onFile(files[0]);
    }
  };

  const getAcceptText = () => {
    if (props.accept?.includes('.pdf')) {
      return props.multiple ? "Drop PDF files here or select files" : "Drop PDF here or select file";
    }
    return props.multiple ? "Drop files here or select files" : "Drop CSV here or select file";
  };

  const getButtonText = () => {
    if (props.multiple) {
      return props.accept?.includes('.pdf') ? "Select PDF files" : "Select files";
    }
    return props.accept?.includes('.pdf') ? "Select PDF file" : "Select file";
  };

  return (
    <div
      className={`card border-dashed ${drag ? "border-sky-500" : "border-gray-200"} text-center`}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault(); setDrag(false);
        if (e.dataTransfer.files?.length) {
          handleFiles(e.dataTransfer.files);
        }
      }}
    >
      <input 
        ref={ref} 
        type="file" 
        accept={props.accept ?? ".csv"} 
        multiple={props.multiple}
        hidden 
        onChange={(e) => {
          if (e.target.files?.length) {
            handleFiles(e.target.files);
          }
        }} 
      />
      <div className="py-10">
        <div className="text-lg font-medium mb-2">{getAcceptText()}</div>
        <button 
          className="flex items-center gap-1 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded border border-blue-600 hover:border-blue-700 transition-colors mx-auto"
          onClick={() => ref.current?.click()}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          {getButtonText()}
        </button>
      </div>
    </div>
  );
}
