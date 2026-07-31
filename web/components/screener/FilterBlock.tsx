import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { X, Settings2 } from "lucide-react";

export type FilterType = "ma_uptrend" | "convergence" | "foreign_buy";

export interface FilterNodeState {
  id: string;
  type: FilterType;
  params: Record<string, string | number | boolean | string[]>;
}

interface FilterBlockProps {
  filter: FilterNodeState;
  onUpdate: (id: string, newFilter: FilterNodeState) => void;
  onRemove: (id: string) => void;
}

export function FilterBlock({ filter, onUpdate, onRemove }: FilterBlockProps) {
  const handleTypeChange = (val: FilterType | null) => {
    if (!val) return;
    // 타입 변경 시 파라미터 초기화
    let defaultParams = {};
    if (val === "ma_uptrend") {
      defaultParams = { timeframe: "daily", selected_lines: ["5", "20"], days: 3 };
    }
    onUpdate(filter.id, { ...filter, type: val, params: defaultParams });
  };

  const handleParamChange = (key: string, val: string | number | boolean | string[]) => {
    onUpdate(filter.id, {
      ...filter,
      params: { ...filter.params, [key]: val }
    });
  };

  const toggleLine = (lineStr: string) => {
    const currentLines: string[] = (filter.params.selected_lines as string[]) || [];
    if (currentLines.includes(lineStr)) {
      handleParamChange("selected_lines", currentLines.filter(l => l !== lineStr));
    } else {
      handleParamChange("selected_lines", [...currentLines, lineStr].sort((a, b) => parseInt(a) - parseInt(b)));
    }
  };

  return (
    <Card className="w-full relative shadow-sm hover:shadow-md transition-shadow">
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-2 right-2 text-muted-foreground hover:text-destructive"
        onClick={() => onRemove(filter.id)}
      >
        <X className="h-4 w-4" />
      </Button>
      <CardHeader className="pb-3 flex flex-row items-center gap-2">
        <Settings2 className="w-5 h-5 text-primary" />
        <CardTitle className="text-lg">필터 조건</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
        <div className="w-full sm:w-[280px] shrink-0">
          <label className="text-xs font-semibold text-muted-foreground mb-1 block">필터 종류 (Type)</label>
          <Select value={filter.type} onValueChange={handleTypeChange}>
            <SelectTrigger>
              <SelectValue placeholder="필터 선택" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ma_uptrend">정배열</SelectItem>
              <SelectItem value="convergence">이평선 수렴</SelectItem>
              <SelectItem value="foreign_buy">외국인 순매수</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex-1 flex gap-4 flex-wrap items-end">
          {filter.type === "ma_uptrend" && (
            <>
              <div className="flex-1 min-w-[120px]">
                <label className="text-xs font-semibold text-muted-foreground mb-1 block">타임프레임</label>
                <Select
                  value={String(filter.params.timeframe || "daily")}
                  onValueChange={(val) => val && handleParamChange("timeframe", val)}
                >
                  <SelectTrigger><SelectValue placeholder="주기" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="daily">일봉 (Daily)</SelectItem>
                    <SelectItem value="minute">분봉 (Minute)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex-auto min-w-[200px]">
                <label className="text-xs font-semibold text-muted-foreground mb-2 block">이평선 선택 (Lines)</label>
                <div className="flex items-center gap-3">
                  {["5", "10", "20", "60", "120"].map((line) => {
                    const isChecked = ((filter.params.selected_lines as string[]) || []).includes(line);
                    return (
                      <div key={line} className="flex items-center space-x-1">
                        <Checkbox
                          id={`${filter.id}-line-${line}`}
                          checked={isChecked}
                          onCheckedChange={() => toggleLine(line)}
                        />
                        <label
                          htmlFor={`${filter.id}-line-${line}`}
                          className="text-sm font-medium leading-none cursor-pointer"
                        >
                          {line}
                        </label>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="flex-1 min-w-[100px]">
                <label className="text-xs font-semibold text-muted-foreground mb-1 block">기간</label>
                <Input
                  type="number"
                  min={1}
                  value={(filter.params.days as string | number) ?? ""}
                  onChange={(e) => handleParamChange("days", e.target.value)}
                />
              </div>
            </>
          )}

          {filter.type === "convergence" && (
            <div className="text-sm text-muted-foreground p-2">
              (개발 예정) 수렴 조건 파라미터 UI
            </div>
          )}

          {filter.type === "foreign_buy" && (
             <div className="text-sm text-muted-foreground p-2">
               (개발 예정) 외국인 순매수 조건 파라미터 UI
             </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
