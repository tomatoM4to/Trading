"use client";

import { useState } from "react";
import { FilterBlock, FilterNodeState } from "./FilterBlock";
import { LogicOp, LogicOperator } from "./LogicOperator";
import { ScreenerResultTable, ScreenerResult } from "./ScreenerResultTable";
import { ChartModal } from "./ChartModal";
import { Button } from "@/components/ui/button";
import { Play, Plus } from "lucide-react";

// ID generator for client-side
const generateId = () => 
  typeof crypto !== 'undefined' && crypto.randomUUID 
    ? crypto.randomUUID() 
    : Math.random().toString(36).substring(2, 9);

interface ScreenerRequestPayload {
  filters: Array<{
    type: string;
    params: Record<string, string | number | boolean | string[]>;
  }>;
  operations: LogicOp[];
}

export function ScreenerBuilder() {
  const [filters, setFilters] = useState<FilterNodeState[]>([
    { 
      id: "initial-filter-1", 
      type: "ma_uptrend", 
      params: { timeframe: "daily", selected_lines: ["5", "20", "60"], days: 3 } 
    }
  ]);
  const [operations, setOperations] = useState<LogicOp[]>([]);
  
  const [results, setResults] = useState<ScreenerResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);

  const addFilter = () => {
    setFilters([...filters, { 
      id: generateId(), 
      type: "ma_uptrend", 
      params: { timeframe: "daily", selected_lines: ["5", "20"], days: 3 } 
    }]);
    if (filters.length > 0) {
      setOperations([...operations, "AND"]);
    }
  };

  const updateFilter = (id: string, newFilter: FilterNodeState) => {
    setFilters(filters.map(f => f.id === id ? newFilter : f));
  };

  const removeFilter = (id: string) => {
    const index = filters.findIndex(f => f.id === id);
    if (index === -1) return;

    const newFilters = [...filters];
    newFilters.splice(index, 1);
    
    const newOps = [...operations];
    if (newOps.length > 0) {
      if (index === 0) {
        newOps.shift();
      } else {
        newOps.splice(index - 1, 1);
      }
    }

    setFilters(newFilters);
    setOperations(newOps);
  };

  const updateOperator = (index: number, op: LogicOp) => {
    const newOps = [...operations];
    newOps[index] = op;
    setOperations(newOps);
  };

  const handleRunQuery = async () => {
    // 1. 유효성 검사
    const invalidFilter = filters.find(f => {
      if (f.type === "ma_uptrend") {
        const days = Number(f.params.days);
        return isNaN(days) || days < 1;
      }
      return false;
    });

    if (invalidFilter) {
      alert("연속 상승 기간(Days)은 1 이상의 숫자로 입력해주세요.");
      return;
    }

    try {
      // 2. 클라이언트 UI 상태를 백엔드 스펙으로 변환
      const mappedFilters = filters.map(f => {
        let backendParams = { ...f.params };
        
        if (f.type === "ma_uptrend") {
          const prefix = f.params.timeframe === "daily" ? "ma_daily_" : "ma";
          const lines = ((f.params.selected_lines as string[]) || []).map((val: string) => `${prefix}${val}`);
          backendParams = {
            lines,
            days: Number(f.params.days)
          };
        }
        
        return {
          type: f.type,
          params: backendParams
        };
      });

      const payload: ScreenerRequestPayload = {
        filters: mappedFilters,
        operations
      };
      
      console.log("Run Screener with payload:", payload);
      setIsLoading(true);
      const response = await fetch("http://localhost:8000/api/screener/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      const data = await response.json();
      
      // 서버에서 전달받은 ticker와 name 기반으로 매핑
      const mappedResults = (data.items || []).map((item: { ticker: string; name: string }) => ({
        ticker: item.ticker,
        name: item.name
      }));
      
      setResults(mappedResults);
    } catch (error: any) {
      console.error("Failed to fetch screener results:", error);
      alert(error.message || "파이프라인 실행 중 오류가 발생했습니다.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-5xl mx-auto p-4 space-y-8">
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-bold tracking-tight">전략 스크리너</h2>
          <Button variant="outline" size="sm" onClick={() => { setFilters([]); setOperations([]); }}>전체 초기화</Button>
        </div>

        <div className="bg-muted/10 border p-6 rounded-xl space-y-4 shadow-inner">
          {filters.length === 0 ? (
            <div className="text-center p-8 text-muted-foreground">
              적용된 필터가 없습니다. 필터를 추가하여 시작하세요.
            </div>
          ) : (
            filters.map((filter, index) => (
              <div key={filter.id}>
                {index > 0 && (
                  <LogicOperator 
                    operator={operations[index - 1]} 
                    onChange={(op) => updateOperator(index - 1, op)} 
                  />
                )}
                <FilterBlock 
                  filter={filter} 
                  onUpdate={updateFilter} 
                  onRemove={removeFilter} 
                />
              </div>
            ))
          )}

          <div className="pt-4 flex justify-center">
            <Button variant="secondary" onClick={addFilter} className="w-full sm:w-auto shadow-sm">
              <Plus className="w-4 h-4 mr-2" /> 필터 조건 추가
            </Button>
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <Button 
            size="lg" 
            className="w-full sm:w-auto font-bold tracking-wide shadow-md"
            onClick={handleRunQuery}
            disabled={isLoading || filters.length === 0}
          >
            <Play className={`w-5 h-5 mr-2 ${isLoading ? 'animate-pulse' : ''}`} /> 
            {isLoading ? "파이프라인 실행 중..." : "파이프라인 실행"}
          </Button>
        </div>
      </div>

      <div className="pt-8 border-t space-y-4">
        <h3 className="text-xl font-semibold">검색 결과</h3>
        <ScreenerResultTable results={results} onRowClick={setSelectedTicker} />
      </div>

      <ChartModal 
        ticker={selectedTicker} 
        isOpen={!!selectedTicker} 
        onClose={() => setSelectedTicker(null)} 
      />
    </div>
  );
}
