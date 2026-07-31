import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export type LogicOp = "AND" | "OR";

interface LogicOperatorProps {
  operator: LogicOp;
  onChange: (val: LogicOp) => void;
}

export function LogicOperator({ operator, onChange }: LogicOperatorProps) {
  return (
    <div className="flex justify-center my-2 relative">
      <div className="absolute top-1/2 left-0 w-full h-[2px] bg-border/50 -z-10" />
      <div className="bg-background px-4">
        <Select value={operator} onValueChange={(v) => onChange(v as LogicOp)}>
          <SelectTrigger className="w-[100px] h-8 rounded-full border-primary/20 bg-muted/50 hover:bg-muted font-bold focus:ring-0">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="AND" className="font-bold">AND</SelectItem>
            <SelectItem value="OR" className="font-bold">OR</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
