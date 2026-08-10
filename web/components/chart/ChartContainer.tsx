"use client";

import { useEffect, useMemo, useState } from "react";
import { ChartDataResponse } from "../../types/market";
import { getChartData } from "../../lib/api";
import { aggregateCandles, aggregateDailyCandles, extractLineSeriesData } from "../../lib/chart-utils";
import LightweightChart, { MA_CONFIGS } from "./LightweightChart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

const MINUTE_TIMEFRAMES = [
  { label: "1m", value: "1", minutes: 1 },
  { label: "3m", value: "3", minutes: 3 },
  { label: "5m", value: "5", minutes: 5 },
  { label: "15m", value: "15", minutes: 15 },
  { label: "30m", value: "30", minutes: 30 },
  { label: "1h", value: "60", minutes: 60 },
];

const DAILY_TIMEFRAMES = [
  { label: "1D", value: "1D" },
  { label: "1W", value: "1W" },
  { label: "1M", value: "1M" },
];

const INDICATORS = [
  { id: "5", label: "5", color: "#ec407a" },
  { id: "10", label: "10", color: "#29b6f6" },
  { id: "20", label: "20", color: "#ffa726" },
  { id: "60", label: "60", color: "#66bb6a" },
  { id: "120", label: "120", color: "#ab47bc" },
  { id: "200", label: "200", color: "#ff7043" },
];

export default function ChartContainer({ ticker }: { ticker: string }) {
  const [data, setData] = useState<ChartDataResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<string>("1");
  const [activeIndicators, setActiveIndicators] = useState<Record<string, boolean>>({
    "5": true,
    "10": true,
    "20": true,
    "60": true,
    "120": true,
    "200": true,
  });

  const isDailyTF = DAILY_TIMEFRAMES.some(tf => tf.value === timeframe);

  const visibleLines = useMemo(() => {
    const result: Record<string, boolean> = {};
    Object.keys(MA_CONFIGS).forEach(key => {
      result[key] = false;
    });
    
    Object.keys(activeIndicators).forEach(num => {
      if (activeIndicators[num]) {
        if (isDailyTF) {
          result[`ma_daily_${num}`] = true;
        } else {
          result[`ma${num}`] = true;
        }
      }
    });
    return result;
  }, [activeIndicators, isDailyTF]);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        // If it's a daily timeframe, we fetch type="daily"
        // If it's a minute timeframe, we fetch type="minute"
        const type = isDailyTF ? "daily" : "minute";
        const res = await getChartData(ticker, 3, type);
        setData(res);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [ticker, isDailyTF]);

  const candleData = useMemo(() => {
    if (!data || !data.data) return [];
    if (isDailyTF) {
      return aggregateDailyCandles(data.data, timeframe as "1D" | "1W" | "1M");
    } else {
      const minutes = parseInt(timeframe, 10);
      return aggregateCandles(data.data, minutes);
    }
  }, [data, timeframe, isDailyTF]);

  const lineData = useMemo(() => {
    if (!data || !data.data) return {};
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result: Record<string, any> = {};
    Object.keys(MA_CONFIGS).forEach((key) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      result[key] = extractLineSeriesData(data.data, key as any, timeframe);
    });
    return result;
  }, [data, timeframe]);

  const toggleMA = (key: string) => {
    setActiveIndicators(prev => ({ ...prev, [key]: !prev[key] }));
  };

  if (loading && !data) return <div className="p-8 text-center text-lg animate-pulse">Loading chart data...</div>;
  if (error) return <div className="p-8 text-center text-red-500">Error: {error}</div>;
  if (!data) return null;

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="text-2xl flex items-center gap-4">
          <span>{data.name}</span>
          <span className="text-sm font-normal text-muted-foreground">{data.ticker}</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center gap-4">
            <span className="text-sm font-semibold text-muted-foreground w-20">Timeframe</span>
            <div className="flex gap-2 border-r pr-4">
              {MINUTE_TIMEFRAMES.map(tf => (
                <Button 
                  key={tf.value} 
                  variant={timeframe === tf.value ? "default" : "outline"}
                  size="sm"
                  onClick={() => setTimeframe(tf.value)}
                >
                  {tf.label}
                </Button>
              ))}
            </div>
            <div className="flex gap-2">
              {DAILY_TIMEFRAMES.map(tf => (
                <Button 
                  key={tf.value} 
                  variant={timeframe === tf.value ? "default" : "outline"}
                  size="sm"
                  onClick={() => setTimeframe(tf.value)}
                >
                  {tf.label}
                </Button>
              ))}
            </div>
          </div>
          
          <div className="flex flex-wrap items-center gap-4">
            <span className="text-sm font-semibold text-muted-foreground w-20">Indicators</span>
            <div className="flex flex-wrap gap-4 items-center">
              {INDICATORS.map((indicator) => (
                <div key={indicator.id} className="flex items-center space-x-2">
                  <Checkbox 
                    id={indicator.id} 
                    checked={activeIndicators[indicator.id] || false} 
                    onCheckedChange={() => toggleMA(indicator.id)} 
                  />
                  <Label 
                    htmlFor={indicator.id} 
                    className="font-medium cursor-pointer" 
                    style={{ color: indicator.color }}
                  >
                    {indicator.label}
                  </Label>
                </div>
              ))}
            </div>
          </div>

          <div className="border rounded-md overflow-hidden bg-background">
            {loading && <div className="absolute inset-0 bg-background/50 flex items-center justify-center z-10 animate-pulse">Loading...</div>}
            <LightweightChart candleData={candleData} lineData={lineData} visibleLines={visibleLines} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
