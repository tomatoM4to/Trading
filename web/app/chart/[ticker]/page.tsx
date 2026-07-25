import ChartContainer from "@/components/chart/ChartContainer";
import Link from "next/link";
import { Button } from "@/components/ui/button";

// Next.js 15+ App Router에서는 params가 Promise일 수 있습니다.
export default async function ChartPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const resolvedParams = await params;
  
  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-7xl mx-auto space-y-6">
        <div>
          <Link href="/">
            <Button variant="outline">← 스크리너로 돌아가기</Button>
          </Link>
        </div>
        
        <ChartContainer ticker={resolvedParams.ticker} />
      </div>
    </main>
  );
}
