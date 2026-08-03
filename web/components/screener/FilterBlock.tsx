import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { X, Settings2, Loader2, CheckCircle2 } from "lucide-react";

export type FilterType = "ma_alignment" | "ma_cross" | "ma_convergence_consolidation" | "ma_convergence_point" | "foreign_net_buy_rank" | "inst_net_buy_rank";

export type FilterStatus = "idle" | "processing" | "done";

export interface FilterNodeState {
  id: string;
  type: FilterType;
  params: Record<string, string | number | boolean | string[]>;
}

interface FilterBlockProps {
  filter: FilterNodeState;
  status?: FilterStatus;
  onUpdate: (id: string, newFilter: FilterNodeState) => void;
  onRemove: (id: string) => void;
}

export function FilterBlock({ filter, status = "idle", onUpdate, onRemove }: FilterBlockProps) {
  const handleTypeChange = (val: FilterType | null) => {
    if (!val) return;
    // 타입 변경 시 파라미터 초기화
    let defaultParams = {};
    if (val === "ma_alignment") {
      defaultParams = { timeframe: "daily", selected_lines: ["5", "20", "60"], duration: 3 };
    } else if (val === "ma_cross") {
      defaultParams = { timeframe: "daily", short_line: "5", long_line: "20", within: 1, direction: "golden" };
    } else if (val === "ma_convergence_consolidation") {
      defaultParams = { timeframe: "daily", selected_lines: ["5", "20", "60"], threshold: 2.0, duration: 3 };
    } else if (val === "ma_convergence_point") {
      defaultParams = { timeframe: "daily", selected_lines: ["5", "20", "60"], threshold: 2.0, within: 1 };
    } else if (val === "foreign_net_buy_rank" || val === "inst_net_buy_rank") {
      defaultParams = { limit: 30 };
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
        <div className="ml-auto mr-8 flex items-center">
           {status === "processing" && <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />}
           {status === "done" && <CheckCircle2 className="w-5 h-5 text-green-500" />}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
        <div className="w-full sm:w-[280px] shrink-0">
          <label className="text-xs font-semibold text-muted-foreground mb-1 block">필터 종류 (Type)</label>
          <Select value={filter.type} onValueChange={handleTypeChange}>
            <SelectTrigger>
              <SelectValue placeholder="필터 선택" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ma_alignment">이평선 정배열</SelectItem>
              <SelectItem value="ma_cross">이평선 크로스</SelectItem>
              <SelectItem value="ma_convergence_consolidation">이평선 수렴 횡보 (유지)</SelectItem>
              <SelectItem value="ma_convergence_point">이평선 수렴 지점 (이벤트)</SelectItem>
              <SelectItem value="foreign_net_buy_rank">외국인 순매수 상위 랭킹</SelectItem>
              <SelectItem value="inst_net_buy_rank">기관 순매수 상위 랭킹</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex-1 flex gap-4 flex-wrap items-end">
          {filter.type === "ma_alignment" && (
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
                <label className="text-xs font-semibold text-muted-foreground mb-1 block">유지 기간</label>
                <Input
                  type="number"
                  min={1}
                  value={(filter.params.duration as string | number) ?? ""}
                  onChange={(e) => handleParamChange("duration", e.target.value)}
                />
              </div>
            </>
          )}

          {filter.type === "ma_cross" && (
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

              <div className="flex-1 min-w-[100px]">
                <label className="text-xs font-semibold text-muted-foreground mb-1 block">단기 이평선</label>
                <Select
                  value={String(filter.params.short_line || "5")}
                  onValueChange={(val) => val && handleParamChange("short_line", val)}
                >
                  <SelectTrigger><SelectValue placeholder="단기" /></SelectTrigger>
                  <SelectContent>
                    {["5", "10", "20"].map(line => <SelectItem key={line} value={line}>{line}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex-1 min-w-[100px]">
                <label className="text-xs font-semibold text-muted-foreground mb-1 block">장기 이평선</label>
                <Select
                  value={String(filter.params.long_line || "20")}
                  onValueChange={(val) => val && handleParamChange("long_line", val)}
                >
                  <SelectTrigger><SelectValue placeholder="장기" /></SelectTrigger>
                  <SelectContent>
                    {["10", "20", "60", "120"].map(line => <SelectItem key={line} value={line}>{line}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex-1 min-w-[120px]">
                <label className="text-xs font-semibold text-muted-foreground mb-1 block">교차 방향</label>
                <Select
                  value={String(filter.params.direction || "golden")}
                  onValueChange={(val) => val && handleParamChange("direction", val)}
                >
                  <SelectTrigger><SelectValue placeholder="방향" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="golden">골든 크로스</SelectItem>
                    <SelectItem value="dead">데드 크로스</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex-1 min-w-[100px]">
                <label className="text-xs font-semibold text-muted-foreground mb-1 block">최근 N일/분 이내</label>
                <Input
                  type="number"
                  min={1}
                  value={(filter.params.within as string | number) ?? ""}
                  onChange={(e) => handleParamChange("within", e.target.value)}
                />
              </div>
            </>
          )}

          {(filter.type === "ma_convergence_consolidation" || filter.type === "ma_convergence_point") && (
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
                <label className="text-xs font-semibold text-muted-foreground mb-1 block">오차율 (%)</label>
                <Input
                  type="number"
                  step="0.1"
                  min={0}
                  value={(filter.params.threshold as string | number) ?? ""}
                  onChange={(e) => handleParamChange("threshold", e.target.value)}
                />
              </div>

              <div className="flex-1 min-w-[100px]">
                <label className="text-xs font-semibold text-muted-foreground mb-1 block">
                  {filter.type === "ma_convergence_consolidation" ? "유지 기간" : "최근 N일/분 이내"}
                </label>
                <Input
                  type="number"
                  min={1}
                  value={
                    (filter.type === "ma_convergence_consolidation" 
                      ? filter.params.duration 
                      : filter.params.within) as string | number ?? ""
                  }
                  onChange={(e) => handleParamChange(filter.type === "ma_convergence_consolidation" ? "duration" : "within", e.target.value)}
                />
              </div>
            </>
          )}

          {(filter.type === "foreign_net_buy_rank" || filter.type === "inst_net_buy_rank") && (
             <div className="text-sm text-muted-foreground p-2 bg-muted/20 rounded-md">
               (KIS 정책상 상위 30개 고정 반환)
             </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
