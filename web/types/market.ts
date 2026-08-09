
export interface ChartDataPoint {
  time: string; // "YYYY-MM-DD HH:MM:SS" 형식
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  
  // 단기 이동평균선 (분봉 기준)
  ma1: number | null;
  ma5: number | null;
  ma10: number | null;
  ma20: number | null;
  ma60: number | null;
  ma120: number | null;
  ma200: number | null;
  
  // 장기 이동평균선 (일봉 기준)
  ma_daily_1: number | null;
  ma_daily_5: number | null;
  ma_daily_20: number | null;
  ma_daily_60: number | null;
  ma_daily_120: number | null;
  ma_daily_200: number | null;
}

export interface ChartDataResponse {
  ticker: string;
  name: string;
  data: ChartDataPoint[];
}
