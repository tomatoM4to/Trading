export interface TopVolumeItem {
  ticker: string;
  name: string;
  volume: number;
}

export interface TopVolumeResponse {
  date: string;
  items: TopVolumeItem[];
}

export interface ChartDataPoint {
  time: string; // "YYYY-MM-DD HH:MM:SS" 형식
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  
  // 단기 이동평균선 (분봉 기준)
  ma1: number | null;
  ma3: number | null;
  ma5: number | null;
  ma15: number | null;
  ma30: number | null;
  ma60: number | null;
  
  // 장기 이동평균선 (일봉 기준)
  ma_daily_1: number | null;
  ma_daily_5: number | null;
  ma_daily_20: number | null;
  ma_daily_100: number | null;
  ma_daily_200: number | null;
}

export interface ChartDataResponse {
  ticker: string;
  name: string;
  data: ChartDataPoint[];
}
