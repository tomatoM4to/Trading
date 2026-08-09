import { useMemo } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { FilterNodeState } from "./FilterBlock";

export interface ScreenerResult {
  ticker: string;
  name: string;
  market?: string | null;
  market_cap?: number | null;
  close?: number | null;
  amount?: number | null;
  change_rate?: number | null;
  filter_values?: Record<string, number>;
  ranks?: Record<string, number>;
  average_rank?: number;
}

interface ScreenerResultTableProps {
  results: ScreenerResult[];
  onRowClick: (ticker: string) => void;
  filters?: FilterNodeState[];
  viewMode?: "default" | "ranking";
}

function formatKoreanCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  
  const trillion = Math.floor(value / 1000000000000);
  const billion = Math.floor((value % 1000000000000) / 100000000);
  
  let result = "";
  if (trillion > 0) {
    result += `${trillion}조`;
    if (billion > 0) result += ` ${billion.toLocaleString()}억`;
  } else if (billion > 0) {
    result += `${billion.toLocaleString()}억`;
  } else {
    result = value.toLocaleString();
  }
  return result;
}

// 필터 타입에 따른 정렬 방향
function getSortType(type: string): "asc" | "desc" {
  if (type === "ma_cross") return "desc"; // 크로스 이격폭은 클수록 좋음
  return "asc"; // 정배열 편차, 수렴 오차, 수급 순위는 모두 낮을수록(오름차순) 좋음
}

// 필터 이름 한글화 헬퍼
function getFilterDisplayName(type: string): string {
  switch (type) {
    case "ma_alignment": return "이평선 정배열";
    case "ma_cross": return "이평선 크로스";
    case "ma_convergence_consolidation": return "수렴 횡보";
    case "ma_convergence_point": return "수렴 지점";
    case "foreign_net_buy_rank": return "외국인 순매수";
    case "inst_net_buy_rank": return "기관 순매수";
    default: return type;
  }
}

export function ScreenerResultTable({ results, onRowClick, filters = [], viewMode = "default" }: ScreenerResultTableProps) {
  const processedResults = useMemo(() => {
    if (results.length === 0) return [];
    if (viewMode === "default") return results;

    const clonedResults = results.map(r => ({ ...r, ranks: {} as Record<string, number>, average_rank: 0 }));

    // 각 필터별로 등수 매기기 (Standard Competition Ranking)
    filters.forEach((filter) => {
      const sortType = getSortType(filter.type);
      
      const sorted = [...clonedResults].sort((a, b) => {
        const valA = a.filter_values?.[filter.id] ?? (sortType === "asc" ? Infinity : -Infinity);
        const valB = b.filter_values?.[filter.id] ?? (sortType === "asc" ? Infinity : -Infinity);
        return sortType === "asc" ? valA - valB : valB - valA;
      });

      let currentRank = 1;
      let previousValue = sorted[0]?.filter_values?.[filter.id];

      sorted.forEach((item, index) => {
        const val = item.filter_values?.[filter.id];
        if (val !== undefined && previousValue !== undefined && val !== previousValue) {
          currentRank = index + 1;
          previousValue = val;
        }
        
        if (val === undefined || val === Infinity || val === -Infinity) {
          item.ranks![filter.id] = 999; // 값이 없는 종목 처리
        } else {
          item.ranks![filter.id] = currentRank;
        }
      });
    });

    // 평균 랭킹 계산
    clonedResults.forEach(item => {
      let sum = 0;
      let count = 0;
      filters.forEach(filter => {
        if (item.ranks && item.ranks[filter.id] !== undefined && item.ranks[filter.id] !== 999) {
          sum += item.ranks[filter.id];
          count++;
        }
      });
      item.average_rank = count > 0 ? Number((sum / count).toFixed(2)) : 999;
    });

    // 최종 정렬 (평균 랭킹 오름차순)
    return clonedResults.sort((a, b) => (a.average_rank || 999) - (b.average_rank || 999));
  }, [results, filters, viewMode]);

  if (results.length === 0) {
    return (
      <div className="text-center p-8 border rounded-lg bg-muted/20 text-muted-foreground">
        결과가 없습니다. 파이프라인을 실행하여 결과를 확인하세요.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-md border bg-card overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[90px]">시장</TableHead>
              <TableHead className="w-[100px]">종목코드</TableHead>
              <TableHead>종목명</TableHead>
              {viewMode === "default" ? (
                <>
                  <TableHead className="text-right">현재가</TableHead>
                  <TableHead className="text-right">등락률</TableHead>
                  <TableHead className="text-right hidden sm:table-cell">당일 거래대금</TableHead>
                  <TableHead className="text-right hidden md:table-cell">시가총액</TableHead>
                </>
              ) : (
                <>
                  {filters.map(f => (
                    <TableHead key={f.id} className="text-right font-semibold text-primary">
                      {getFilterDisplayName(f.type)}
                    </TableHead>
                  ))}
                  <TableHead className="text-right font-bold text-orange-500">평균 순위</TableHead>
                </>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {processedResults.map((row) => {
              const isPositive = row.change_rate && row.change_rate > 0;
              const isNegative = row.change_rate && row.change_rate < 0;
              const changeColor = isPositive ? "text-red-500" : isNegative ? "text-blue-500" : "";
              
              return (
                <TableRow 
                  key={row.ticker} 
                  className="cursor-pointer hover:bg-muted/50 transition-colors"
                  onClick={() => onRowClick(row.ticker)}
                >
                  <TableCell>
                    {row.market && (
                      <span className={`px-2 py-0.5 rounded text-xs font-bold border ${
                        row.market === "KOSPI"
                          ? "bg-red-500/10 text-red-500 border-red-500/20"
                          : row.market === "KOSDAQ"
                          ? "bg-blue-500/10 text-blue-500 border-blue-500/20"
                          : "bg-muted text-muted-foreground"
                      }`}>
                        {row.market}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="font-medium text-muted-foreground">{row.ticker}</TableCell>
                  <TableCell className="font-bold">{row.name}</TableCell>
                  
                  {viewMode === "default" ? (
                    <>
                      <TableCell className={`text-right font-bold ${changeColor}`}>
                        {row.close ? row.close.toLocaleString() : "-"}
                      </TableCell>
                      <TableCell className={`text-right font-bold ${changeColor}`}>
                        {row.change_rate !== null && row.change_rate !== undefined 
                          ? `${row.change_rate > 0 ? "+" : ""}${row.change_rate}%` 
                          : "-"}
                      </TableCell>
                      <TableCell className="text-right hidden sm:table-cell text-muted-foreground font-medium">
                        {formatKoreanCurrency(row.amount)}
                      </TableCell>
                      <TableCell className="text-right hidden md:table-cell text-muted-foreground font-medium">
                        {formatKoreanCurrency(row.market_cap)}
                      </TableCell>
                    </>
                  ) : (
                    <>
                      {filters.map(f => (
                        <TableCell key={f.id} className="text-right font-mono">
                          {row.ranks?.[f.id] && row.ranks[f.id] !== 999 
                            ? <span className="bg-primary/10 px-2 py-1 rounded text-primary font-bold">{row.ranks[f.id]}위</span> 
                            : "-"}
                        </TableCell>
                      ))}
                      <TableCell className="text-right font-mono font-bold text-orange-500">
                        {row.average_rank !== 999 ? `${row.average_rank}위` : "-"}
                      </TableCell>
                    </>
                  )}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
