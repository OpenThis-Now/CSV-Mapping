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
    completedReviews,
    queueStatus, 
    isQueueProcessing,
    isQueuePaused,
    startAnalysis, 
    stopAnalysis, 
    approveSuggestion, 
    rejectSuggestion, 
    loadExistingSuggestions,
    loadCompletedReviews,
    startAutoQueue,
    getQueueStatus,
    startQueuePolling,
    stopQueuePolling,
    pauseQueue,
    resumeQueue
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
    loadCompletedReviews(projectId);
    getQueueStatus(projectId);
  }, [projectId]);

  // Auto-refresh suggestions when queue processing
  useEffect(() => {
    if (isQueueProcessing) {
      const interval = setInterval(() => {
        loadExistingSuggestions(projectId);
        loadCompletedReviews(projectId);
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
      {queueStatus && (queueStatus.queued > 0 || queueStatus.processing > 0 || queueStatus.ready > 0 || queueStatus.autoApproved > 0) && (
        <div className="space-y-4">
          <AIQueueStatus 
            stats={{
              queued: queueStatus.queued,
              processing: queueStatus.processing,
              ready: queueStatus.ready || 0,
              autoApproved: queueStatus.autoApproved || 0
            }}
          />
          
        </div>
      )}



      {/* Ready for Review Section */}
      {!!suggestions.length && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold text-gray-800">Ready for Review</h2>
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
                                {(() => {
                                  // Extract fields to review from AI explanation
                                  const explanation = item.details.explanation || '';
                                  const fieldsMatch = explanation.match(/FIELDS_TO_REVIEW:\s*([^\.]+)/i);
                                  const fieldsToReview = fieldsMatch ? fieldsMatch[1].trim() : null;
                                  
                                  if (fieldsToReview && fieldsToReview.toLowerCase() !== 'none') {
                                    return (
                                      <p className="text-sm text-blue-600">
                                        <span className="font-medium">AI recommendation fields to review:</span> {fieldsToReview}
                                      </p>
                                    );
                                  } else {
                                    return (
                                      <p className="text-sm text-green-600">
                                        <span className="font-medium">AI recommendation:</span> No fields need review - this is a strong match
                                      </p>
                                    );
                                  }
                                })()}
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
        </div>
      )}

      {/* Reviewed Section */}
      {!!completedReviews.length && (
        <div className="mt-8 space-y-4">
          <h2 className="text-xl font-semibold text-gray-800">Reviewed</h2>
          <div className="space-y-3">
            {completedReviews.map((review, index) => {
              const productName = review.customer_fields?.["Product"] || 
                                 review.customer_fields?.["Product_name"] || 
                                 review.customer_fields?.["product"] || 
                                 review.customer_fields?.["Produkt"] ||
                                 "Unknown product";
              
              const isExpanded = expanded.has(`completed-${review.customer_row_index}`);
              const toggleKey = `completed-${review.customer_row_index}`;
              
              // Status styling
              const statusStyles = {
                approved: "bg-green-50 border-green-200 text-green-800",
                rejected: "bg-red-50 border-red-200 text-red-800", 
                auto_approved: "bg-blue-50 border-blue-200 text-blue-800"
              };
              
              const statusLabels = {
                approved: "Approved",
                rejected: "Rejected",
                auto_approved: "Auto-approved"
              };

              return (
                <div key={review.customer_row_index} className={`rounded-lg border-2 p-4 ${statusStyles[review.decision as keyof typeof statusStyles] || 'bg-gray-50 border-gray-200'}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="text-sm opacity-75">
                        Review for: <span className="font-medium">"{productName}"</span>
                      </div>
                      <div className="px-2 py-1 text-xs font-medium rounded-full bg-white/50">
                        {statusLabels[review.decision as keyof typeof statusLabels] || review.decision}
                      </div>
                    </div>
                    <button 
                      className="p-1 hover:bg-white/20 rounded transition-colors"
                      onClick={() => {
                        const newExpanded = new Set(expanded);
                        if (newExpanded.has(toggleKey)) {
                          newExpanded.delete(toggleKey);
                        } else {
                          newExpanded.add(toggleKey);
                        }
                        setExpanded(newExpanded);
                      }}
                    >
                      {isExpanded ? (
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
                  
                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-white/30 text-sm">
                      {/* Input vs Database Comparison */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                        <div>
                          <div className="font-medium mb-2 text-xs uppercase tracking-wide opacity-75">Input Data</div>
                          <div className="bg-white/20 p-3 rounded text-xs">
                            <div className="font-semibold mb-1">{productName}</div>
                            <div className="space-y-1 opacity-75">
                              <div><span className="font-medium">Supplier:</span> {review.customer_fields?.["Supplier"] || review.customer_fields?.["Supplier_name"] || review.customer_fields?.["vendor"] || "-"}</div>
                              <div><span className="font-medium">Art.no:</span> {review.customer_fields?.["Art.no"] || review.customer_fields?.["Article_number"] || review.customer_fields?.["article"] || "-"}</div>
                              <div><span className="font-medium">Market:</span> {review.customer_fields?.["Market"] || review.customer_fields?.["market"] || "-"}</div>
                              <div><span className="font-medium">Language:</span> {review.customer_fields?.["Language"] || review.customer_fields?.["language"] || "-"}</div>
                              {review.customer_fields?.["Location_ID"] && <div><span className="font-medium">Location ID:</span> {review.customer_fields["Location_ID"]}</div>}
                              {review.customer_fields?.["Product_ID"] && <div><span className="font-medium">Product ID:</span> {review.customer_fields["Product_ID"]}</div>}
                              {review.customer_fields?.["Description"] && <div><span className="font-medium">Description:</span> {review.customer_fields["Description"]}</div>}
                              {review.customer_fields?.["SDS-URL"] && <div><span className="font-medium">SDS URL:</span> <a href={review.customer_fields["SDS-URL"]} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">{review.customer_fields["SDS-URL"]}</a></div>}
                              {review.customer_fields?.["Unique_ID"] && <div><span className="font-medium">Unique ID:</span> {review.customer_fields["Unique_ID"]}</div>}
                              {review.customer_fields?.["MSDSkey"] && <div><span className="font-medium">MSDS Key:</span> {review.customer_fields["MSDSkey"]}</div>}
                              {review.customer_fields?.["Revision_date"] && <div><span className="font-medium">Revision Date:</span> {review.customer_fields["Revision_date"]}</div>}
                              {review.customer_fields?.["Expire_date"] && <div><span className="font-medium">Expire Date:</span> {review.customer_fields["Expire_date"]}</div>}
                            </div>
                          </div>
                        </div>
                        
                        <div>
                          <div className="font-medium mb-2 text-xs uppercase tracking-wide opacity-75">Database Match</div>
                          <div className="bg-white/20 p-3 rounded text-xs">
                            {review.approved_suggestion ? (
                              <>
                                <div className="font-semibold mb-1">
                                  {review.approved_suggestion.database_fields_json?.["Product_name"]}
                                </div>
                                <div className="space-y-1 opacity-75">
                                  <div><span className="font-medium">Supplier:</span> {review.approved_suggestion.database_fields_json?.["Supplier_name"] || "-"}</div>
                                  <div><span className="font-medium">Art.no:</span> {review.approved_suggestion.database_fields_json?.["Article_number"] || "-"}</div>
                                  <div><span className="font-medium">Market:</span> {review.approved_suggestion.database_fields_json?.["Market"] || "-"}</div>
                                  <div><span className="font-medium">Language:</span> {review.approved_suggestion.database_fields_json?.["Language"] || "-"}</div>
                                </div>
                                {review.approved_suggestion.confidence && (
                                  <div className="mt-2 text-xs font-medium">
                                    AI Confidence: {Math.round(review.approved_suggestion.confidence * 100)}%
                                  </div>
                                )}
                              </>
                            ) : (
                              <div className="opacity-75">No match selected</div>
                            )}
                          </div>
                        </div>
                      </div>
                      
                      {review.ai_summary && (
                        <div className="mt-2">
                          <div className="font-medium">AI Summary:</div>
                          <div className="text-xs opacity-75 mt-1 bg-white/10 p-2 rounded">{review.ai_summary}</div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
