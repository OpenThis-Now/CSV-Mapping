import api, { AiSuggestionItem, MatchResultItem } from "@/lib/api";
import { useEffect, useState } from "react";
import { useAI } from "@/contexts/AIContext";
import CountryFlag from "@/components/CountryFlag";
import AIQueueStatus from "@/components/AIQueueStatus";

export default function AIDeep({ projectId }: { projectId: number }) {
  const [results, setResults] = useState<MatchResultItem[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const { 
    isAnalyzing, 
    thinkingStep, 
    suggestions, 
    queueStatus, 
    isQueueProcessing,
    startAnalysis, 
    stopAnalysis, 
    approveSuggestion, 
    rejectSuggestion, 
    loadExistingSuggestions,
    startAutoQueue,
    getQueueStatus,
    startQueuePolling,
    stopQueuePolling
  } = useAI();

  const refresh = async () => {
    try {
    const res = await api.get<MatchResultItem[]>(`/projects/${projectId}/results`);
      // Store all results for product name lookup, but filter for display
      setResults(res.data);
      const aiResults = res.data.filter(r => r.decision === "sent_to_ai");
      console.log("Loaded AI results:", aiResults.length, "items");
    } catch (error) {
      console.error("Failed to load results:", error);
    }
  };
  useEffect(() => { 
    refresh(); 
    loadExistingSuggestions(projectId);
    getQueueStatus(projectId);
  }, [projectId]);

  // Auto-refresh suggestions when queue processing
  useEffect(() => {
    if (isQueueProcessing) {
      const interval = setInterval(() => {
        loadExistingSuggestions(projectId);
        getQueueStatus(projectId);
      }, 3000);
      
      return () => clearInterval(interval);
    }
  }, [isQueueProcessing, projectId]);

  const sendAI = async () => {
    // Only send items that are marked as "sent_to_ai"
    const aiResults = results.filter(r => r.decision === "sent_to_ai");
    const selectedAiResults = selected.filter(id => 
      aiResults.some(r => r.customer_row_index === id)
    );
    await startAnalysis(projectId, selectedAiResults);
  };

  const handleApproveSuggestion = async (suggestion: AiSuggestionItem) => {
    await approveSuggestion(suggestion, projectId);
    // Remove from selected list since it's no longer available for AI
    setSelected(prev => prev.filter(id => id !== suggestion.customer_row_index));
    // Refresh the results to update the decision status
    await refresh();
  };

  const handleRejectSuggestion = async (suggestion: AiSuggestionItem) => {
    await rejectSuggestion(suggestion, projectId);
    // Remove from selected list since it's no longer available for AI
    setSelected(prev => prev.filter(id => id !== suggestion.customer_row_index));
    // Refresh the results to update the decision status
    await refresh();
  };

  return (
    <div className="space-y-4">

      {/* AI Queue Status */}
      {queueStatus && (
        <AIQueueStatus 
          stats={{
            queued: queueStatus.queued,
            processing: queueStatus.processing,
            ready: queueStatus.ready,
            autoApproved: queueStatus.autoApproved
          }}
        />
      )}


      {isAnalyzing && (
        <div className="card border-l-4 border-l-blue-500 bg-blue-50">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="flex space-x-1">
                <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"></div>
                <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
              </div>
              <div className="text-sm font-medium text-blue-900">
                AI is analyzing your products...
              </div>
            </div>
            <button 
              onClick={stopAnalysis}
              className="px-3 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200"
            >
              Stop Analysis
            </button>
          </div>
          
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 border-2 border-blue-200 border-t-blue-500 rounded-full animate-spin"></div>
              <span className="text-sm text-blue-800">
                {thinkingStep === 0 && "Analyzing product data..."}
                {thinkingStep === 1 && "Searching database..."}
                {thinkingStep === 2 && "Comparing products..."}
                {thinkingStep === 3 && "Generating suggestions..."}
                {thinkingStep === 4 && "Completing analysis..."}
              </span>
            </div>
            
            <div className="w-full bg-blue-100 rounded-full h-2">
              <div 
                className="bg-blue-500 h-2 rounded-full transition-all duration-1000 ease-out"
                style={{ width: `${((thinkingStep + 1) / 5) * 100}%` }}
              ></div>
            </div>
            
            <div className="text-xs text-blue-600">
              AI analysis in progress... This may take 1-5 minutes depending on the number of products. You can navigate to other pages while the analysis is running.
            </div>
          </div>
        </div>
      )}

      {!!suggestions.length && (
        <div className="space-y-6">
          {(() => {
            // Group suggestions by customer_row_index
            const groupedSuggestions = suggestions.reduce((acc, suggestion) => {
              if (!acc[suggestion.customer_row_index]) {
                acc[suggestion.customer_row_index] = [];
              }
              acc[suggestion.customer_row_index].push(suggestion);
              return acc;
            }, {} as Record<number, AiSuggestionItem[]>);

            return Object.entries(groupedSuggestions).map(([rowIndex, productSuggestions]) => {
              const firstSuggestion = productSuggestions[0];
              
              // Get input data for this row
              const inputData = results.find(r => r.customer_row_index === parseInt(rowIndex));
              
              // Use the import product name instead of database product name
              const productName = inputData?.customer_preview["Product"] || 
                                 inputData?.customer_preview["Product_name"] || 
                                 inputData?.customer_preview["product"] || 
                                 inputData?.customer_preview["Produkt"] ||
                                 "Unknown product";
              
              // Field mapping to show same names for Input and Database
              const fieldMapping: Record<string, string> = {
                'Product_name': 'Product',
                'product': 'Product',
                'Produkt': 'Product',
                'Supplier_name': 'Supplier',
                'vendor': 'Supplier',
                'Leverantör': 'Supplier',
                'Article_number': 'Art.no',
                'article': 'Art.no',
                'Artikelnummer': 'Art.no',
                'Market': 'Market',
                'Marknad': 'Market',
                'Language': 'Language',
                'Språk': 'Language',
                'Price': 'Price',
                'Category': 'Category',
                'Description': 'Description'
              };

              // Create results array with all suggestions
              const analysisResults = productSuggestions.map((suggestion, index) => {
                const confidence = suggestion.confidence;
                const confidencePercent = Math.round(confidence * 100);
                
                // Determine color based on confidence level
                let color = "";
                if (confidence <= 0.4) {
                  color = "bg-red-500";
                } else if (confidence <= 0.6) {
                  color = "bg-yellow-500";
                } else {
                  color = "bg-green-500";
                }

                return {
                  label: index === 0 ? "Recommended match" : "Alternative match",
                  conf: confidencePercent,
                  value: suggestion.database_fields_json["Product_name"],
                  color: color,
                  uniqueKey: `${rowIndex}-${index}`, // Unique key for each match
                  details: {
                    supplier: suggestion.database_fields_json["Supplier_name"],
                    artno: suggestion.database_fields_json["Article_number"],
                    market: suggestion.database_fields_json["Market"],
                    language: suggestion.database_fields_json["Language"],
                    explanation: suggestion.rationale,
                    input: inputData ? inputData.customer_preview : {},
                    database: suggestion.database_fields_json,
                    suggestion: suggestion
                  }
                };
              });
              
              return (
                <div key={rowIndex} className="space-y-4">
                  {/* Header */}
                  <div className="bg-white rounded-2xl shadow p-6">
                    <h1 className="text-2xl mb-6"><span className="font-bold">Review for:</span> "{productName}"</h1>
                    
                    <div className="space-y-4">
                      {analysisResults.map((item, i) => (
                        <div key={i} className="p-3 border rounded-lg">
                          <div className="flex justify-between items-center mb-1">
                            <span className="font-medium">{item.label}</span>
                            <span className="text-sm text-gray-500">{item.conf}%</span>
                          </div>
                          <div className="w-full bg-gray-200 rounded-full h-2">
                            <div
                              className={`${item.color} h-2 rounded-full`}
                              style={{ width: `${item.conf}%` }}
                            ></div>
                          </div>
                          <div className="flex justify-between items-center mt-2">
                            <p className="font-semibold">{item.value}</p>
                        <button 
                              className="p-1 hover:bg-gray-100 rounded"
                              onClick={() => {
                                const newExpanded = new Set(expanded);
                                if (newExpanded.has(item.uniqueKey)) {
                                  newExpanded.delete(item.uniqueKey);
                                } else {
                                  newExpanded.add(item.uniqueKey);
                                }
                                setExpanded(newExpanded);
                              }}
                            >
                              {expanded.has(item.uniqueKey) ? (
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                                </svg>
                              ) : (
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                </svg>
                              )}
                        </button>
                      </div>

                          {expanded.has(item.uniqueKey) && item.details && (
                            <div className="mt-4 space-y-3 border-t pt-3 text-sm">
                              <div className="bg-blue-50 p-3 rounded">
                                <p className="font-semibold text-blue-700">AI explanation:</p>
                                <p className="mb-2">{item.details.explanation}</p>
                                <p className="text-sm text-blue-600">
                                  <span className="font-medium">AI recommendation fields to review:</span> The fields the AI have explained isn't a 100% match, ex. "Article number" or "Article number & Product name"
                                </p>
                    </div>
                              <div className="grid grid-cols-2 gap-4">
                                <div>
                                  <p className="font-medium mb-1">Input</p>
                                  {Object.entries(item.details.input).map(([key, val]) => (
                                    <p key={key}>
                                      <span className="font-semibold">{fieldMapping[key] || key}:</span> {String(val)}
                                    </p>
                                  ))}
                                </div>
                                <div>
                                  <p className="font-medium mb-1">Database</p>
                                  {Object.entries(item.details.database).map(([key, val]) => (
                                    <p key={key}>
                                      <span className="font-semibold">{fieldMapping[key] || key}:</span> {String(val)}
                                    </p>
          ))}
                                </div>
                              </div>
                              <div className="flex gap-3 mt-3">
                                <button 
                                  className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700"
                                  onClick={() => handleApproveSuggestion(item.details.suggestion)}
                                >
                                  Select this match
                                </button>
                                <button 
                                  className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700"
                                  onClick={() => handleRejectSuggestion(item.details.suggestion)}
                                >
                                  Reject
                                </button>
                              </div>
                            </div>
                          )}
                          </div>
                      ))}
                    </div>
                  </div>
                </div>
              );
            });
          })()}
        </div>
      )}
    </div>
  );
}
