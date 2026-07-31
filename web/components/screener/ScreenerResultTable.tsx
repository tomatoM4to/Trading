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
}

interface ScreenerResultTableProps {
  results: ScreenerResult[];
  onRowClick: (ticker: string) => void;
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
    <div className="rounded-md border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[120px]">종목코드</TableHead>
            <TableHead>종목명</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {results.map((row) => (
            <TableRow 
              key={row.ticker} 
              className="cursor-pointer hover:bg-muted/50 transition-colors"
              onClick={() => onRowClick(row.ticker)}
            >
              <TableCell className="font-medium text-primary">{row.ticker}</TableCell>
              <TableCell>{row.name}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
