import { createContext, useContext, useState, ReactNode, useRef } from 'react';
import { AiSuggestionItem } from '@/lib/api';
import { useToast } from './ToastContext';

interface AIContextType {
  // AI Analysis State
  isAnalyzing: boolean;
  thinkingStep: number;
  suggestions: AiSuggestionItem[];
  
  // AI Analysis Actions
  startAnalysis: (projectId: number, selectedIndices: number[]) => Promise<void>;
  startAnalysisForSentToAI: (projectId: number) => Promise<void>;
  stopAnalysis: () => void;
  clearSuggestions: () => void;
  approveSuggestion: (suggestion: AiSuggestionItem, projectId: number) => Promise<void>;
  rejectSuggestion: (suggestion: AiSuggestionItem, projectId: number) => Promise<void>;
}

const AIContext = createContext<AIContextType | undefined>(undefined);

export function AIProvider({ children }: { children: ReactNode }) {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [thinkingStep, setThinkingStep] = useState(0);
  const [suggestions, setSuggestions] = useState<AiSuggestionItem[]>([]);
  const { showToast } = useToast();
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  const startAnalysis = async (projectId: number, selectedIndices: number[]) => {
    // Warn if too many rows selected
    if (selectedIndices.length > 10) {
      showToast(`AI analysis limited to first 10 rows (${selectedIndices.length} selected). Consider analyzing in smaller batches.`, 'warning');
    }
    
    setIsAnalyzing(true);
    setThinkingStep(0);
    setSuggestions([]);
    
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
      setSuggestions(res.data);
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

      // Reject the match result - this sets it to "not_approved"
      await api.post(`/projects/${projectId}/reject`, { ids: [matchResult.id] });
      
      // Remove this product from the AI suggestions
      setSuggestions(prev => prev.filter(s => s.customer_row_index !== suggestion.customer_row_index));
      
      showToast("Product rejected and marked as 'not_approved'!", 'success');
    } catch (error) {
      console.error("Failed to reject suggestion:", error);
      showToast("Could not reject match. Please try again.", 'error');
    }
  };

  return (
    <AIContext.Provider value={{
      isAnalyzing,
      thinkingStep,
      suggestions,
      startAnalysis,
      startAnalysisForSentToAI,
      stopAnalysis,
      clearSuggestions,
      approveSuggestion,
      rejectSuggestion
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
