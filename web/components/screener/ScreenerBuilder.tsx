"use client";

import { useState, useEffect } from "react";
import { FilterBlock, FilterNodeState, FilterStatus } from "./FilterBlock";
import { LogicOp, LogicOperator } from "./LogicOperator";
import { ScreenerResultTable, ScreenerResult } from "./ScreenerResultTable";
import { ChartModal } from "./ChartModal";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { Button } from "@/components/ui/button";
import { Play, Plus, ArrowRightLeft } from "lucide-react";
import { toast } from "sonner";

// ID generator for client-side
const generateId = () =>
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).substring(2, 9);

interface ScreenerRequestPayload {
  filters: Array<{
    id: string;
    type: string;
    params: Record<string, string | number | boolean | string[]>;
  }>;
  operations: LogicOp[];
}

export function ScreenerBuilder() {
  const [filters, setFilters] = useState<FilterNodeState[]>([
    {
      id: "initial-filter-1",
      type: "ma_alignment",
      params: { timeframe: "daily", selected_lines: ["5", "20", "60"], duration: 3 }
    }
  ]);
  const [operations, setOperations] = useState<LogicOp[]>([]);

  const [results, setResults] = useState<ScreenerResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [filterStatuses, setFilterStatuses] = useState<Record<string, FilterStatus>>({});
  const [remainingCount, setRemainingCount] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<"default" | "ranking">("default");

  const [startTime, setStartTime] = useState<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState<number>(0);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isLoading && startTime !== null) {
      interval = setInterval(() => {
        setElapsedMs(Date.now() - startTime);
      }, 100);
    }
    return () => clearInterval(interval);
  }, [isLoading, startTime]);

  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);

  const addFilter = () => {
    setFilters([...filters, {
      id: generateId(),
      type: "ma_alignment",
      params: { timeframe: "daily", selected_lines: ["5", "20", "60"], duration: 3 }
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
      if (f.type === "ma_alignment" || f.type === "ma_convergence_consolidation") {
        const duration = Number(f.params.duration);
        return isNaN(duration) || duration < 1;
      }
      if (f.type === "ma_cross" || f.type === "ma_convergence_point") {
        const within = Number(f.params.within);
        return isNaN(within) || within < 1;
      }
      return false;
    });

    if (invalidFilter) {
      toast.error("유지 기간(duration) 또는 교차 기준일(within)은 1 이상의 숫자로 입력해주세요.");
      return;
    }

    try {
      // 2. 클라이언트 UI 상태를 백엔드 스펙으로 변환
      const mappedFilters = filters.map(f => {
        let backendParams = { ...f.params };

        if (f.type === "ma_alignment") {
          const prefix = f.params.timeframe === "daily" ? "ma_daily_" : "ma";
          const lines = ((f.params.selected_lines as string[]) || []).map((val: string) => `${prefix}${val}`);
          backendParams = {
            lines,
            duration: Number(f.params.duration)
          };
        } else if (f.type === "ma_cross") {
          const prefix = f.params.timeframe === "daily" ? "ma_daily_" : "ma";
          backendParams = {
            short_line: `${prefix}${f.params.short_line}`,
            long_line: `${prefix}${f.params.long_line}`,
            direction: f.params.direction,
            within: Number(f.params.within)
          };
        } else if (f.type === "ma_convergence_consolidation") {
          const prefix = f.params.timeframe === "daily" ? "ma_daily_" : "ma";
          const lines = ((f.params.selected_lines as string[]) || []).map((val: string) => `${prefix}${val}`);
          backendParams = {
            lines,
            threshold: Number(f.params.threshold),
            duration: Number(f.params.duration)
          };
        } else if (f.type === "ma_convergence_point") {
          const prefix = f.params.timeframe === "daily" ? "ma_daily_" : "ma";
          const lines = ((f.params.selected_lines as string[]) || []).map((val: string) => `${prefix}${val}`);
          backendParams = {
            lines,
            threshold: Number(f.params.threshold),
            within: Number(f.params.within)
          };
        } else if (f.type === "foreign_net_buy_rank" || f.type === "inst_net_buy_rank") {
          backendParams = { limit: 30 };
        }

        return {
          id: f.id,
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
      setStartTime(Date.now());
      setElapsedMs(0);
      
      const initialStatuses: Record<string, FilterStatus> = {};
      filters.forEach(f => initialStatuses[f.id] = "idle");
      setFilterStatuses(initialStatuses);
      setRemainingCount(null);
      setResults([]);

      const ctrl = new AbortController();

      const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      await fetchEventSource(`${API_BASE_URL}/api/screener/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: ctrl.signal,
        async onmessage(ev) {
          const data = JSON.parse(ev.data);
          if (data.type === "start") {
            setFilterStatuses(prev => ({ ...prev, [data.filter_id]: "processing" }));
          } else if (data.type === "progress") {
            setFilterStatuses(prev => ({ ...prev, [data.filter_id]: "done" }));
            setRemainingCount(data.remaining);
          } else if (data.type === "complete") {
            const mappedResults = (data.items || []).map((item: any) => ({
              ticker: item.ticker,
              name: item.name,
              market: item.market,
              market_cap: item.market_cap,
              close: item.close,
              amount: item.amount,
              change_rate: item.change_rate,
              filter_values: item.filter_values || {}
            }));
            setResults(mappedResults);
            setIsLoading(false);
            ctrl.abort(); // Prevent auto-reconnect
          } else if (data.type === "error") {
            toast.error(data.message);
            setIsLoading(false);
            ctrl.abort(); // 스트림 강제 종료 (throw 에러로 인한 Next.js 오버레이 방지)
            return;
          }
        },
        onerror(err) {
          setIsLoading(false);
          throw err;
        }
      });

    } catch (error: unknown) {
      console.error("Failed to fetch screener results:", error);
      toast.error((error as Error).message || "실행 중 오류가 발생했습니다.");
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
                  status={filterStatuses[filter.id] || "idle"}
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

        <div className="flex justify-end pt-2 items-center gap-4">
          {remainingCount !== null && (
            <div className="text-sm font-semibold text-primary/80 animate-in fade-in slide-in-from-right-4">
              실시간 남은 종목: <span className="text-2xl text-primary font-bold">{remainingCount.toLocaleString()}</span> 개
            </div>
          )}
          
          {(isLoading || elapsedMs > 0) && (
            <div className="text-sm font-mono font-medium bg-muted/50 px-3 py-1.5 rounded-md border text-muted-foreground flex items-center shadow-sm">
              ⏱ {(elapsedMs / 1000).toFixed(1)}s
            </div>
          )}

          <Button
            size="lg"
            className="w-full sm:w-auto font-bold tracking-wide shadow-md"
            onClick={handleRunQuery}
            disabled={isLoading || filters.length === 0}
          >
            <Play className={`w-5 h-5 mr-2 ${isLoading ? 'animate-pulse' : ''}`} />
            {isLoading ? "실행 중..." : "실행"}
          </Button>
        </div>
      </div>

      <div className="pt-8 border-t space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xl font-semibold">검색 결과</h3>
          {results.length > 0 && (
            <Button 
              variant="outline" 
              size="sm" 
              onClick={() => setViewMode(prev => prev === "default" ? "ranking" : "default")}
            >
              <ArrowRightLeft className="w-4 h-4 mr-2" />
              {viewMode === "default" ? "랭킹 뷰로 보기" : "기본 뷰로 보기"}
            </Button>
          )}
        </div>
        <ScreenerResultTable results={results} onRowClick={setSelectedTicker} filters={filters} viewMode={viewMode} />
      </div>

      <ChartModal
        ticker={selectedTicker}
        isOpen={!!selectedTicker}
        onClose={() => setSelectedTicker(null)}
      />
    </div>
  );
}
