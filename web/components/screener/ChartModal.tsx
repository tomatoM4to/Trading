import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import dynamic from "next/dynamic";
import { Suspense } from "react";

// Load ChartContainer dynamically as it uses canvas/browser APIs
const ChartContainer = dynamic(() => import("@/components/chart/ChartContainer"), {
  ssr: false,
  loading: () => <div className="h-[600px] flex items-center justify-center">차트 로딩 중...</div>
});

interface ChartModalProps {
  ticker: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export function ChartModal({ ticker, isOpen, onClose }: ChartModalProps) {
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl sm:max-w-5xl w-[90vw] h-[80vh] sm:h-auto flex flex-col">
        <DialogHeader>
          <DialogTitle>차트 뷰 - {ticker}</DialogTitle>
        </DialogHeader>
        <div className="mt-4 border rounded-md overflow-hidden bg-background flex-1 min-h-0">
          {ticker && (
            <Suspense fallback={<div className="h-[600px] flex items-center justify-center">로딩 중...</div>}>
              <ChartContainer ticker={ticker} />
            </Suspense>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
