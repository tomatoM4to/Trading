import { ChartDataResponse } from "../types/market";

// 환경변수나 기본 localhost를 바라보도록 설정
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";


/**
 * 특정 종목의 다중 타임프레임 차트 데이터를 가져옵니다.
 */
export async function getChartData(ticker: string, days: number = 3, type: "minute" | "daily" = "minute"): Promise<ChartDataResponse> {
  const res = await fetch(`${API_BASE_URL}/market/chart/${ticker}?days=${days}&type=${type}`, {
    cache: "no-store",
  });
  
  if (!res.ok) {
    throw new Error(`Failed to fetch chart data for ${ticker}`);
  }
  
  return res.json();
}
