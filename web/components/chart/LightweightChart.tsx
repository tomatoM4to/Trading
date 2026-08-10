"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, CandlestickSeries, LineSeries, HistogramSeries } from "lightweight-charts";
import { AggregatedCandle, LineDataPoint } from "../../lib/chart-utils";

export const MA_CONFIGS: Record<string, { color: string; title: string; lineWidth?: number }> = {
  ma5: { color: "#ec407a", title: "5", lineWidth: 2 },
  ma10: { color: "#29b6f6", title: "10", lineWidth: 2 },
  ma20: { color: "#ffa726", title: "20", lineWidth: 2 },
  ma60: { color: "#66bb6a", title: "60", lineWidth: 2 },
  ma120: { color: "#ab47bc", title: "120", lineWidth: 2 },
  ma200: { color: "#ff7043", title: "200", lineWidth: 2 },
  ma_daily_5: { color: "#ec407a", title: "5", lineWidth: 2 },
  ma_daily_10: { color: "#29b6f6", title: "10", lineWidth: 2 },
  ma_daily_20: { color: "#ffa726", title: "20", lineWidth: 2 },
  ma_daily_60: { color: "#66bb6a", title: "60", lineWidth: 2 },
  ma_daily_120: { color: "#ab47bc", title: "120", lineWidth: 2 },
  ma_daily_200: { color: "#ff7043", title: "200", lineWidth: 2 },
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

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#d1d5db",
      },
      // Lightweight Charts Grid Options
      // Source: https://tradingview.github.io/lightweight-charts/docs/api/interfaces/GridOptions
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.1)" },
        horzLines: { color: "rgba(255, 255, 255, 0.1)" },
      },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight || 400,
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

    // 거래량 시리즈 생성 (오버레이)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#26a69a',
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: '', // 오버레이로 설정
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8, // 상단 80%부터 시작하여 하단 20%만 차지함
        bottom: 0,
      },
    });
    seriesRef.current['volume'] = volumeSeries;

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

    const resizeObserver = new ResizeObserver(entries => {
      if (entries.length === 0 || entries[0].target !== chartContainerRef.current) {
        return;
      }
      const newRect = entries[0].contentRect;
      chart.applyOptions({ height: newRect.height, width: newRect.width });
    });
    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
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
    
    // Update volume data
    if (seriesRef.current['volume']) {
      seriesRef.current['volume'].setData(
        candleData.map(c => ({
          time: c.time,
          value: c.volume,
          color: c.close >= c.open ? 'rgba(239, 83, 80, 0.4)' : 'rgba(38, 166, 154, 0.4)'
        }))
      );
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

  return <div ref={chartContainerRef} style={{ width: "100%", height: "100%" }} />;
}
