"use client";

import { useEffect, useState } from "react";
import { TopVolumeResponse } from "../types/market";
import { getTopVolume } from "../lib/api";
import Link from "next/link";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export default function Home() {
  const [data, setData] = useState<TopVolumeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchTopVolume() {
      try {
        setLoading(true);
        const result = await getTopVolume();
        setData(result);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    fetchTopVolume();
  }, []);

  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <Card>
          <CardHeader>
            <CardTitle className="text-3xl font-bold tracking-tight text-slate-900">Trading Dashboard</CardTitle>
            <CardDescription>
              실시간 거래대금/거래량 상위 종목 스크리너 
              {data?.date && ` (기준일: ${data.date})`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="py-10 text-center animate-pulse text-slate-500">
                시장 데이터를 불러오는 중입니다...
              </div>
            ) : error ? (
              <div className="py-10 text-center text-red-500">
                에러가 발생했습니다: {error}
              </div>
            ) : (
              <div className="border rounded-md overflow-hidden bg-white">
                <Table>
                  <TableCaption>거래량 상위 30개 종목 리스트입니다.</TableCaption>
                  <TableHeader>
                    <TableRow className="bg-slate-100 hover:bg-slate-100">
                      <TableHead className="w-16 text-center font-bold">순위</TableHead>
                      <TableHead className="w-32 font-bold">종목코드</TableHead>
                      <TableHead className="font-bold">종목명</TableHead>
                      <TableHead className="text-right font-bold">거래량</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data?.items.map((item, index) => (
                      <TableRow key={item.ticker} className="group hover:bg-slate-50 transition-colors">
                        <TableCell className="text-center font-medium text-slate-500">
                          {index + 1}
                        </TableCell>
                        <TableCell className="font-mono text-slate-600">
                          {item.ticker}
                        </TableCell>
                        <TableCell className="font-bold text-slate-900">
                          <Link href={`/chart/${item.ticker}`} className="hover:text-blue-600 hover:underline">
                            {item.name}
                          </Link>
                        </TableCell>
                        <TableCell className="text-right font-mono text-slate-700">
                          {item.volume.toLocaleString()}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
