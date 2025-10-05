import React from 'react';

type BulkActionBarProps = {
  count: number;
  onApprove: () => void;
  onReject: () => void;
  onSend: () => void;
};

export function BulkActionBar({ count, onApprove, onReject, onSend }: BulkActionBarProps) {
  if (count === 0) return null;
  
  return (
    <div
      aria-live="polite"
      className="fixed inset-x-3 bottom-3 z-50 mx-auto max-w-6xl"
    >
      <div className="flex items-center justify-between rounded-2xl border bg-white/80 p-2 shadow-lg backdrop-blur supports-[backdrop-filter]:backdrop-blur">
        <span className="px-2 text-sm text-slate-600">{count} markerade</span>
        <div className="flex items-center gap-2">
          <button 
            onClick={onApprove} 
            className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium bg-slate-100 hover:bg-slate-200"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
            Approve
          </button>
          <button 
            onClick={onReject} 
            className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium border hover:bg-slate-50"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
            Reject
          </button>
          <button 
            onClick={onSend} 
            className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium bg-black text-white hover:opacity-90"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
            </svg>
            Send to AI
          </button>
        </div>
      </div>
    </div>
  );
}
