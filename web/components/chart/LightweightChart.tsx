"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, CandlestickSeries, LineSeries } from "lightweight-charts";
import { AggregatedCandle, LineDataPoint } from "../../lib/chart-utils";

export const MA_CONFIGS: Record<string, { color: string; title: string; lineWidth?: number }> = {
  ma1: { color: "#ffeb3b", title: "1m (Debug)" },
  ma5: { color: "#ff9f4f", title: "5m" },
  ma10: { color: "#ff6f00", title: "10m" },
  ma20: { color: "#df4f00", title: "20m" },
  ma60: { color: "#bf2f00", title: "60m" },
  ma120: { color: "#9c27b0", title: "120m" },
  ma_daily_1: { color: "#8bc34a", title: "1D (Debug)", lineWidth: 2 },
  ma_daily_5: { color: "#4caf50", title: "5d", lineWidth: 2 },
  ma_daily_20: { color: "#2196f3", title: "20d", lineWidth: 2 },
  ma_daily_60: { color: "#3f51b5", title: "60d", lineWidth: 3 },
  ma_daily_120: { color: "#9c27b0", title: "120d", lineWidth: 3 },
};

interface LightweightChartProps {
  candleData: AggregatedCandle[];
  lineData: Record<string, LineDataPoint[]>;
  visibleLines: Record<string, boolean>;
}

export default function LightweightChart({ candleData, lineData, visibleLines }: LightweightChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesRef = useRef<Record<string, ISeriesApi<any>>>({});

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const handleResize = () => {
      chartRef.current?.applyOptions({ width: chartContainerRef.current?.clientWidth });
    };

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#333",
      },
      width: chartContainerRef.current.clientWidth,
      height: 600,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      }
    });

    chartRef.current = chart;
    
    // 캔들 시리즈 생성 (한국 업비트/키움증권 스타일: 상승 빨강, 하락 파랑)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#ef5350',
      downColor: '#26a69a',
      borderVisible: false,
      wickUpColor: '#ef5350',
      wickDownColor: '#26a69a',
    });
    seriesRef.current['candles'] = candleSeries;
    
    // 이평선 시리즈 생성
    Object.entries(MA_CONFIGS).forEach(([key, config]) => {
      const lineSeries = chart.addSeries(LineSeries, {
        color: config.color,
        lineWidth: (config as any).lineWidth || 1,
        title: config.title,
        visible: visibleLines[key] ?? false,
      });
      seriesRef.current[key] = lineSeries;
    });

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, []); // Only run once on mount

  // Props(데이터, 가시성) 변경 시 차트 업데이트 로직
  useEffect(() => {
    if (!chartRef.current) return;
    
    // Update candle data
    if (seriesRef.current['candles']) {
      seriesRef.current['candles'].setData(candleData);
    }
    
    // Update line data & visibility
    Object.keys(MA_CONFIGS).forEach(key => {
      const series = seriesRef.current[key];
      if (series) {
        if (lineData[key] && lineData[key].length > 0) {
          series.setData(lineData[key]);
        }
        series.applyOptions({
          visible: visibleLines[key] ?? false,
        });
      }
    });
  }, [candleData, lineData, visibleLines]);

  return <div ref={chartContainerRef} style={{ width: "100%", height: "600px" }} />;
}
