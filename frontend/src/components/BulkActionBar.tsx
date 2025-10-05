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
            className="inline-flex items-center rounded-xl px-3 py-2 text-sm font-medium bg-slate-100 hover:bg-slate-200"
          >
            Approve
          </button>
          <button 
            onClick={onReject} 
            className="inline-flex items-center rounded-xl px-3 py-2 text-sm font-medium border hover:bg-slate-50"
          >
            Reject
          </button>
          <button 
            onClick={onSend} 
            className="inline-flex items-center rounded-xl px-3 py-2 text-sm font-medium bg-black text-white hover:opacity-90"
          >
            Send to AI
          </button>
        </div>
      </div>
    </div>
  );
}
