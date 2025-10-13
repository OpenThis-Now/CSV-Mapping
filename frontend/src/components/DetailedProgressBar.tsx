import React from 'react';

interface DetailedProgressBarProps {
  total: number;
  approved: number;
  worklist: number;
  rejected: number;
  pending: number;
}

export default function DetailedProgressBar({ total, approved, worklist, rejected, pending }: DetailedProgressBarProps) {
  if (total === 0) {
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>Progress</span>
          <span>0% completed</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div className="bg-gray-300 h-2 rounded-full" style={{ width: '100%' }}></div>
        </div>
      </div>
    );
  }

  // Calculate percentages
  const approvedPct = (approved / total) * 100;
  const worklistPct = (worklist / total) * 100;
  const rejectedPct = (rejected / total) * 100;
  const pendingPct = (pending / total) * 100;
  
  const completedPct = approvedPct + worklistPct; // Exclude rejected from completed percentage
  const totalCompleted = approved + worklist; // Exclude rejected from completed count

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>Progress</span>
        <span>{Math.round(completedPct)}% completed ({totalCompleted}/{total})</span>
      </div>
      
      <div className="w-full bg-gray-200 rounded-full h-2 relative overflow-hidden">
        {/* Approved (dark blue) */}
        {approvedPct > 0 && (
          <div 
            className="bg-blue-600 h-2 absolute left-0 top-0 transition-all duration-300" 
            style={{ width: `${approvedPct}%` }}
            title={`${approved} approved (${Math.round(approvedPct)}%)`}
          ></div>
        )}
        
        {/* Worklist (light blue) */}
        {worklistPct > 0 && (
          <div 
            className="bg-blue-400 h-2 absolute transition-all duration-300" 
            style={{ 
              width: `${worklistPct}%`,
              left: `${approvedPct}%`
            }}
            title={`${worklist} ready for DB import (${Math.round(worklistPct)}%)`}
          ></div>
        )}
        
        {/* Rejected (light red) */}
        {rejectedPct > 0 && (
          <div 
            className="bg-red-300 h-2 absolute transition-all duration-300" 
            style={{ 
              width: `${rejectedPct}%`,
              left: `${approvedPct + worklistPct}%`
            }}
            title={`${rejected} rejected (${Math.round(rejectedPct)}%)`}
          ></div>
        )}
        
        {/* Pending (light gray) */}
        {pendingPct > 0 && (
          <div 
            className="bg-gray-200 h-2 absolute transition-all duration-300" 
            style={{ 
              width: `${pendingPct}%`,
              left: `${approvedPct + worklistPct + rejectedPct}%`
            }}
            title={`${pending} pending (${Math.round(pendingPct)}%)`}
          ></div>
        )}
      </div>
      
      {/* Legend */}
      <div className="flex flex-wrap gap-2 text-xs">
        {approved > 0 && (
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-1 font-medium text-blue-800">
            ✓ {approved} approved
          </span>
        )}
        {worklist > 0 && (
          <span className="inline-flex items-center gap-1 rounded-full bg-purple-50 px-2 py-1 font-medium text-purple-700">
            🕐 {worklist} ready for DB import
          </span>
        )}
        {rejected > 0 && (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-1 font-medium text-red-700">
            ✗ {rejected} rejected
          </span>
        )}
        {pending > 0 && (
          <span className="inline-flex items-center gap-1 rounded-full bg-yellow-100 px-2 py-1 font-medium text-yellow-800">
            ⚠ {pending} pending
          </span>
        )}
      </div>
    </div>
  );
}
