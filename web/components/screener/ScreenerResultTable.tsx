import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export interface ScreenerResult {
  ticker: string;
  name: string;
  market?: string | null;
  market_cap?: number | null;
  close?: number | null;
  amount?: number | null;
  change_rate?: number | null;
}

interface ScreenerResultTableProps {
  results: ScreenerResult[];
  onRowClick: (ticker: string) => void;
}

function formatKoreanCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  
  // value is in KRW (원)
  const trillion = Math.floor(value / 1000000000000);
  const billion = Math.floor((value % 1000000000000) / 100000000);
  
  let result = "";
  if (trillion > 0) {
    result += `${trillion}조`;
    if (billion > 0) result += ` ${billion.toLocaleString()}억`;
  } else if (billion > 0) {
    result += `${billion.toLocaleString()}억`;
  } else {
    // For smaller amounts, just show the localized string
    result = value.toLocaleString();
  }
  return result;
}

export function ScreenerResultTable({ results, onRowClick }: ScreenerResultTableProps) {
  if (results.length === 0) {
    return (
      <div className="text-center p-8 border rounded-lg bg-muted/20 text-muted-foreground">
        결과가 없습니다. 파이프라인을 실행하여 결과를 확인하세요.
      </div>
    );
  }

  return (
    <div className="rounded-md border bg-card overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[90px]">시장</TableHead>
            <TableHead className="w-[100px]">종목코드</TableHead>
            <TableHead>종목명</TableHead>
            <TableHead className="text-right">현재가</TableHead>
            <TableHead className="text-right">등락률</TableHead>
            <TableHead className="text-right hidden sm:table-cell">당일 거래대금</TableHead>
            <TableHead className="text-right hidden md:table-cell">시가총액</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {results.map((row) => {
            const isPositive = row.change_rate && row.change_rate > 0;
            const isNegative = row.change_rate && row.change_rate < 0;
            // Tailwind CSS colors commonly used for stocks in Korea (Red: Up, Blue: Down)
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
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
