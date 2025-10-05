import React from 'react';

interface PDFProcessingProgressProps {
  status: {
    has_active_processing: boolean;
    processing_run_id?: number;
    status?: string;
    total_files?: number;
    processed_files?: number;
    successful_files?: number;
    failed_files?: number;
    current_file?: string;
    progress_percentage?: number;
    started_at?: string;
    finished_at?: string;
    error_message?: string;
  } | null;
}

export default function PDFProcessingProgress({ status }: PDFProcessingProgressProps) {
  if (!status || !status.has_active_processing) {
    return null;
  }

  const progress = status.progress_percentage || 0;
  const totalFiles = status.total_files || 0;
  const processedFiles = status.processed_files || 0;
  const successfulFiles = status.successful_files || 0;
  const failedFiles = status.failed_files || 0;

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'uploading':
        return 'bg-blue-500';
      case 'running':
        return 'bg-green-500';
      case 'completed':
        return 'bg-green-600';
      case 'failed':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'uploading':
        return 'Uploading files...';
      case 'running':
        return 'Processing PDFs...';
      case 'completed':
        return 'Processing completed!';
      case 'failed':
        return 'Processing failed';
      default:
        return 'Processing...';
    }
  };

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-blue-900 flex items-center gap-2">
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
          PDF Processing Progress
        </h3>
        <span className="text-sm text-blue-700 font-medium">
          {Math.round(progress)}%
        </span>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-blue-100 rounded-full h-3 mb-3">
        <div 
          className={`h-3 rounded-full transition-all duration-500 ${getStatusColor(status.status || 'running')}`}
          style={{ width: `${progress}%` }}
        ></div>
      </div>

      {/* Status Text */}
      <div className="text-sm text-blue-800 mb-2">
        {getStatusText(status.status || 'running')}
      </div>

      {/* Current File */}
      {status.current_file && (
        <div className="text-sm text-blue-700 mb-2">
          Currently processing: <span className="font-medium">{status.current_file}</span>
        </div>
      )}

      {/* File Statistics */}
      <div className="flex items-center gap-4 text-sm text-blue-700">
        <span>
          Files: {processedFiles}/{totalFiles}
        </span>
        {successfulFiles > 0 && (
          <span className="text-green-700">
            ✓ {successfulFiles} successful
          </span>
        )}
        {failedFiles > 0 && (
          <span className="text-red-700">
            ✗ {failedFiles} failed
          </span>
        )}
      </div>

      {/* Error Message */}
      {status.error_message && (
        <div className="mt-3 p-2 bg-red-100 border border-red-200 rounded text-sm text-red-800">
          <strong>Error:</strong> {status.error_message}
        </div>
      )}

      {/* Completion Message */}
      {status.status === 'completed' && (
        <div className="mt-3 p-2 bg-green-100 border border-green-200 rounded text-sm text-green-800">
          ✓ PDF processing completed successfully! The extracted data has been added to your imports.
        </div>
      )}
    </div>
  );
}
