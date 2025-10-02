import { createContext, useContext, useState, ReactNode, useRef } from 'react';
import { AiSuggestionItem } from '@/lib/api';
import { useToast } from './ToastContext';

interface AIContextType {
  // AI Analysis State
  isAnalyzing: boolean;
  thinkingStep: number;
  suggestions: AiSuggestionItem[];
  completedReviews: any[];
  
  // AI Queue State
  queueStatus: {
    queued: number;
    processing: number;
    ready: number;
    autoApproved: number;
  } | null;
  isQueueProcessing: boolean;
  isQueuePaused: boolean;
  
  // AI Analysis Actions
  startAnalysis: (projectId: number, selectedIndices: number[]) => Promise<void>;
  startAnalysisForSentToAI: (projectId: number) => Promise<void>;
  stopAnalysis: () => void;
  clearSuggestions: () => void;
  approveSuggestion: (suggestion: AiSuggestionItem, projectId: number) => Promise<void>;
  rejectSuggestion: (suggestion: AiSuggestionItem, projectId: number) => Promise<void>;
  loadExistingSuggestions: (projectId: number) => Promise<void>;
  loadCompletedReviews: (projectId: number) => Promise<void>;
  
  // AI Queue Actions
  startAutoQueue: (projectId: number) => Promise<void>;
  getQueueStatus: (projectId: number) => Promise<void>;
  startQueuePolling: (projectId: number) => void;
  stopQueuePolling: () => void;
  pauseQueue: (projectId: number) => Promise<void>;
  resumeQueue: (projectId: number) => Promise<void>;
  checkAndResumeQueue: (projectId: number) => Promise<void>;
}

const AIContext = createContext<AIContextType | undefined>(undefined);

export function AIProvider({ children }: { children: ReactNode }) {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [thinkingStep, setThinkingStep] = useState(0);
  const [suggestions, setSuggestions] = useState<AiSuggestionItem[]>([]);
  const [completedReviews, setCompletedReviews] = useState<any[]>([]);
  const [queueStatus, setQueueStatus] = useState<{
    queued: number;
    processing: number;
    ready: number;
    autoApproved: number;
  } | null>(null);
  const [isQueueProcessing, setIsQueueProcessing] = useState(false);
  const [isQueuePaused, setIsQueuePaused] = useState(false);
  const { showToast } = useToast();
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const queuePollingRef = useRef<NodeJS.Timeout | null>(null);

  const loadExistingSuggestions = async (projectId: number) => {
    try {
      const { default: api } = await import('@/lib/api');
      const response = await api.get(`/projects/${projectId}/ai/suggestions`);
      setSuggestions(response.data);
    } catch (error) {
      console.error("Failed to load existing AI suggestions:", error);
    }
  };

  const loadCompletedReviews = async (projectId: number) => {
    try {
      const { default: api } = await import('@/lib/api');
      const response = await api.get(`/projects/${projectId}/ai/completed-reviews`);
      setCompletedReviews(response.data);
    } catch (error) {
      console.error("Failed to load completed AI reviews:", error);
    }
  };

  const startAnalysis = async (projectId: number, selectedIndices: number[]) => {
    // Warn if too many rows selected
    if (selectedIndices.length > 10) {
      showToast(`AI analysis limited to first 10 rows (${selectedIndices.length} selected). Consider analyzing in smaller batches.`, 'info');
    }
    
    setIsAnalyzing(true);
    setThinkingStep(0);
    // Don't clear existing suggestions - they will be merged with new ones
    
    // Simulate thinking steps
    const thinkingSteps = [
      `Analyzing ${Math.min(selectedIndices.length, 10)} products...`,
      "Searching database...",
      "Comparing products...",
      "Generating AI suggestions...",
      "Completing analysis..."
    ];
    
    const stepInterval = setInterval(() => {
      setThinkingStep(prev => {
        if (prev < thinkingSteps.length - 1) {
          return prev + 1;
        }
        return prev;
      });
    }, 2000); // Increased from 1000ms to 2000ms for better visibility
    
    // Set a timeout to prevent infinite hanging
    timeoutRef.current = setTimeout(() => {
      console.log("AI analysis timeout - forcing completion");
      clearInterval(stepInterval);
      setIsAnalyzing(false);
      setThinkingStep(0);
      showToast("AI analysis timed out. Try analyzing fewer products at once (max 10).", 'error');
    }, 300000); // 5 minutes timeout

    try {
      const { default: api } = await import('@/lib/api');
      const res = await api.post<AiSuggestionItem[]>(`/projects/${projectId}/ai/suggest`, { 
        customer_row_indices: selectedIndices, 
        max_suggestions: 3 
      });
      console.log("AI suggestions received:", res.data);
      
      // Merge new suggestions with existing ones, replacing any existing suggestions for the same customer_row_index
      setSuggestions(prev => {
        const newSuggestions = res.data;
        const existingSuggestions = prev.filter(s => 
          !newSuggestions.some(ns => ns.customer_row_index === s.customer_row_index)
        );
        return [...existingSuggestions, ...newSuggestions];
      });
    } catch (error) {
      console.error("AI suggest failed:", error);
      showToast("AI analysis failed. Try analyzing fewer products at once (max 10) or check your internet connection.", 'error');
    } finally {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      clearInterval(stepInterval);
      // Complete analysis immediately without showing final step
      setIsAnalyzing(false);
      setThinkingStep(0);
    }
  };

  const startAnalysisForSentToAI = async (projectId: number) => {
    try {
      const { default: api } = await import('@/lib/api');
      
      // Get all products with "sent_to_ai" status
      const results = await api.get(`/projects/${projectId}/results`);
      const sentToAI = results.data.filter((r: any) => r.decision === "sent_to_ai");
      
      if (sentToAI.length === 0) {
        showToast("No products to analyze.", 'info');
        return;
      }
      
      const selectedIndices = sentToAI.map((r: any) => r.customer_row_index);
      await startAnalysis(projectId, selectedIndices);
    } catch (error) {
      console.error("Failed to start AI analysis for sent_to_ai products:", error);
      showToast("Could not start AI analysis.", 'error');
    }
  };

  const stopAnalysis = () => {
    console.log("Stopping AI analysis manually");
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    setIsAnalyzing(false);
    setThinkingStep(0);
    setSuggestions([]);
  };

  const clearSuggestions = () => {
    setSuggestions([]);
  };

  const approveSuggestion = async (suggestion: AiSuggestionItem, projectId: number) => {
    try {
      const { default: api } = await import('@/lib/api');
      
      console.log("Approving suggestion:", suggestion);
      
      // Use the new AI approval endpoint that tracks which suggestion was approved
      const response = await api.post(`/projects/${projectId}/approve-ai`, { 
        customer_row_index: suggestion.customer_row_index,
        ai_suggestion_id: suggestion.id || 0 // We need to get the actual AI suggestion ID
      });
      
      console.log("Approval response:", response.data);
      
      // Remove this product from the AI suggestions
      setSuggestions(prev => prev.filter(s => s.customer_row_index !== suggestion.customer_row_index));
      
      // Reload completed reviews
      await loadCompletedReviews(projectId);
      
      showToast("Product approved and match saved!", 'success');
    } catch (error) {
      console.error("Failed to approve suggestion:", error);
      showToast("Could not approve match. Please try again.", 'error');
    }
  };

  const rejectSuggestion = async (suggestion: AiSuggestionItem, projectId: number) => {
    try {
      const { default: api } = await import('@/lib/api');
      
      // Get current results to find the match result ID
      const results = await api.get(`/projects/${projectId}/results`);
      const matchResult = results.data.find((r: any) => r.customer_row_index === suggestion.customer_row_index);
      
      if (!matchResult) {
        showToast("Could not find match for this row.", 'error');
        return;
      }

      // Reject the match result - this sets it to "rejected"
      await api.post(`/projects/${projectId}/reject`, { ids: [matchResult.id] });
      
      // Remove this product from the AI suggestions
      setSuggestions(prev => prev.filter(s => s.customer_row_index !== suggestion.customer_row_index));
      
      // Reload completed reviews
      await loadCompletedReviews(projectId);
      
      showToast("Product rejected and marked as 'rejected'!", 'success');
    } catch (error) {
      console.error("Failed to reject suggestion:", error);
      showToast("Could not reject match. Please try again.", 'error');
    }
  };

  // AI Queue Functions
  const startAutoQueue = async (projectId: number) => {
    try {
      const { default: api } = await import('@/lib/api');
      const response = await api.post(`/projects/${projectId}/ai/auto-queue`);
      
      showToast(`Successfully queued ${response.data.queued_count} products for AI analysis!`, 'success');
      
      // Set analyzing immediately when auto queue starts
      setIsAnalyzing(true);
      setIsQueueProcessing(true);
      
      // Start polling for queue status
      startQueuePolling(projectId);
      
      return response.data;
    } catch (error) {
      console.error("Failed to start auto queue:", error);
      showToast("Could not start AI queue. Please try again.", 'error');
    }
  };

  const getQueueStatus = async (projectId: number) => {
    try {
      const { default: api } = await import('@/lib/api');
      const response = await api.get(`/projects/${projectId}/ai/queue-status`);
      setQueueStatus(response.data);
      
      // Update processing state
      const isProcessing = response.data.processing > 0 || response.data.queued > 0;
      setIsQueueProcessing(isProcessing);
      
      // Update isAnalyzing based on queue processing status
      // Keep analyzing state if either manual analysis or queue processing is active
      if (!isProcessing && isAnalyzing) {
        // Only stop analyzing if no queue processing and no manual analysis
        // This will be handled by the individual analysis functions
      }
      
      return response.data;
    } catch (error) {
      console.error("Failed to get queue status:", error);
    }
  };

  const startQueuePolling = (projectId: number) => {
    // Clear existing polling
    if (queuePollingRef.current) {
      clearInterval(queuePollingRef.current);
    }
    
    // Start new polling every 1 second for real-time updates
    queuePollingRef.current = setInterval(async () => {
      await getQueueStatus(projectId);
      await loadExistingSuggestions(projectId); // Refresh suggestions in real-time
      
      // If no more items in queue, stop polling
      if (queueStatus && queueStatus.queued === 0 && queueStatus.processing === 0) {
        stopQueuePolling();
      }
    }, 1000);
  };

  const stopQueuePolling = () => {
    if (queuePollingRef.current) {
      clearInterval(queuePollingRef.current);
      queuePollingRef.current = null;
    }
    setIsQueueProcessing(false);
    
    // Only stop analyzing if no manual analysis is currently running
    // Check if we have any active timeout or manual analysis
    if (isAnalyzing && !timeoutRef.current) {
      // No manual analysis timeout active, so it's safe to stop analyzing
      setIsAnalyzing(false);
    }
  };

  const pauseQueue = async (projectId: number) => {
    try {
      const { default: api } = await import('@/lib/api');
      await api.post(`/projects/${projectId}/ai/pause-queue`);
      setIsQueuePaused(true);
      showToast("AI matching paused", 'info');
    } catch (error) {
      console.error("Failed to pause queue:", error);
      showToast("Could not pause AI matching. Please try again.", 'error');
    }
  };

  const resumeQueue = async (projectId: number) => {
    try {
      const { default: api } = await import('@/lib/api');
      await api.post(`/projects/${projectId}/ai/resume-queue`);
      setIsQueuePaused(false);
      showToast("AI matching resumed", 'success');
    } catch (error) {
      console.error("Failed to resume queue:", error);
      showToast("Could not resume AI matching. Please try again.", 'error');
    }
  };

  const checkAndResumeQueue = async (projectId: number) => {
    try {
      const { default: api } = await import('@/lib/api');
      const response = await api.get(`/projects/${projectId}/ai/queue-status`);
      const isProcessing = response.data.processing > 0 || response.data.queued > 0;
      
      if (isProcessing) {
        setIsQueueProcessing(true);
        setIsAnalyzing(true);
        setQueueStatus(response.data);
        startQueuePolling(projectId);
      }
      
      return response.data;
    } catch (error) {
      console.error("Failed to check queue status:", error);
    }
  };

  return (
    <AIContext.Provider value={{
      isAnalyzing,
      thinkingStep,
      suggestions,
      completedReviews,
      queueStatus,
      isQueueProcessing,
      isQueuePaused,
      startAnalysis,
      startAnalysisForSentToAI,
      stopAnalysis,
      clearSuggestions,
      approveSuggestion,
      rejectSuggestion,
      loadExistingSuggestions,
      loadCompletedReviews,
      startAutoQueue,
      getQueueStatus,
      startQueuePolling,
      stopQueuePolling,
      pauseQueue,
      resumeQueue,
      checkAndResumeQueue
    }}>
      {children}
    </AIContext.Provider>
  );
}

export function useAI() {
  const context = useContext(AIContext);
  if (context === undefined) {
    throw new Error('useAI must be used within an AIProvider');
  }
  return context;
}
