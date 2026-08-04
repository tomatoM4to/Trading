import { ChartDataPoint } from "../types/market";
import { Time } from "lightweight-charts";

export interface AggregatedCandle {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/**
 * 1분봉 데이터(ChartDataPoint)를 지정된 분(minutes) 단위 캔들로 그룹핑합니다.
 */
export function aggregateCandles(
  data: ChartDataPoint[],
  minutes: number
): AggregatedCandle[] {
  if (minutes <= 1) {
    return data.map(parseToTimestamp);
  }

  const result: AggregatedCandle[] = [];
  let currentCandle: AggregatedCandle | null = null;
  let currentGroupTime = 0; // 초 단위 타임스탬프

  for (const point of data) {
    // "YYYY-MM-DD HH:MM:SS" -> KST 기준 타임스탬프(초)로 변환
    const dateObj = new Date(point.time.replace(" ", "T") + "+09:00");
    const timestampSec = Math.floor(dateObj.getTime() / 1000) + 9 * 60 * 60;
    
    // 타임프레임 구간(초) 계산
    const intervalSec = minutes * 60;
    // 09:00 정각부터 깔끔하게 그룹핑되도록 내림 연산
    const groupTime = Math.floor(timestampSec / intervalSec) * intervalSec;

    if (!currentCandle || groupTime !== currentGroupTime) {
      if (currentCandle) {
        result.push(currentCandle);
      }
      currentGroupTime = groupTime;
      currentCandle = {
        time: groupTime as Time,
        open: point.open,
        high: point.high,
        low: point.low,
        close: point.close,
        volume: point.volume,
      };
    } else {
      currentCandle.high = Math.max(currentCandle.high, point.high);
      currentCandle.low = Math.min(currentCandle.low, point.low);
      currentCandle.close = point.close;
      currentCandle.volume += point.volume;
    }
  }

  // 마지막 캔들 꼬리 밀어넣기
  if (currentCandle) {
    result.push(currentCandle);
  }

  return result;
}

/**
 * 1분봉 데이터를 가공 없이 단순 Unix 타임스탬프 형식으로 파싱
 */
function parseToTimestamp(point: ChartDataPoint): AggregatedCandle {
  const dateObj = new Date(point.time.replace(" ", "T") + "+09:00");
  return {
    time: (Math.floor(dateObj.getTime() / 1000) + 9 * 60 * 60) as Time,
    open: point.open,
    high: point.high,
    low: point.low,
    close: point.close,
    volume: point.volume,
  };
}

/**
 * 일봉 데이터를 기반으로 주봉(1W) 또는 월봉(1M) 캔들로 그룹핑합니다.
 */
export function aggregateDailyCandles(
  data: ChartDataPoint[],
  timeframe: "1D" | "1W" | "1M"
): AggregatedCandle[] {
  if (timeframe === "1D") {
    return data.map(parseToTimestamp);
  }

  const result: AggregatedCandle[] = [];
  let currentCandle: AggregatedCandle | null = null;
  let currentGroupKey = "";

  for (const point of data) {
    const dateObj = new Date(point.time.replace(" ", "T") + "+09:00");
    const timestampSec = Math.floor(dateObj.getTime() / 1000) + 9 * 60 * 60;
    
    let groupKey = "";
    if (timeframe === "1M") {
      // 월봉: YYYY-MM
      const year = dateObj.getFullYear();
      const month = dateObj.getMonth(); // 0-11
      groupKey = `${year}-${month}`;
    } else if (timeframe === "1W") {
      // 주봉: 월요일 기준 주간 그룹핑
      const dayOfWeek = dateObj.getDay(); // 0: Sun, 1: Mon, ...
      const diff = dateObj.getDate() - dayOfWeek + (dayOfWeek === 0 ? -6 : 1); // 월요일로 맞춤
      const monday = new Date(dateObj.setDate(diff));
      monday.setHours(0, 0, 0, 0);
      groupKey = monday.getTime().toString();
    }

    if (!currentCandle || groupKey !== currentGroupKey) {
      if (currentCandle) {
        result.push(currentCandle);
      }
      currentGroupKey = groupKey;
      currentCandle = {
        time: timestampSec as Time, // 해당 주의 첫 거래일 타임스탬프
        open: point.open,
        high: point.high,
        low: point.low,
        close: point.close,
        volume: point.volume,
      };
    } else {
      currentCandle.high = Math.max(currentCandle.high, point.high);
      currentCandle.low = Math.min(currentCandle.low, point.low);
      currentCandle.close = point.close;
      currentCandle.volume += point.volume;
    }
  }

  if (currentCandle) {
    result.push(currentCandle);
  }

  return result;
}

export interface LineDataPoint {
  time: Time;
  value: number;
}

/**
 * 전체 데이터 배열에서 특정 이동평균선(예: 'ma3', 'ma_daily_5') 데이터를 추출하되,
 * 현재 선택된 timeframe(예: '30', '1D')에 맞춰 캔들과 동일한 시간축(Time)을 갖도록 그룹핑합니다.
 * 각 그룹 내에서 마지막 유효한 값을 해당 캔들의 이평선 값으로 사용합니다.
 */
export function extractLineSeriesData(
  data: ChartDataPoint[],
  key: keyof ChartDataPoint,
  timeframe: string
): LineDataPoint[] {
  const result: LineDataPoint[] = [];
  const isDailyTF = ["1D", "1W", "1M"].includes(timeframe);

  let currentGroupKey = "";
  let currentGroupTime: Time | null = null;
  let lastValue: number | null = null;

  for (const point of data) {
    const val = point[key];
    if (val === null || val === undefined || typeof val !== "number") {
      continue;
    }

    const dateObj = new Date(point.time.replace(" ", "T") + "+09:00");
    const timestampSec = Math.floor(dateObj.getTime() / 1000) + 9 * 60 * 60;
    
    let groupKey = "";
    let gTime: Time = timestampSec as Time;

    if (isDailyTF) {
      if (timeframe === "1D") {
        groupKey = point.time.split(" ")[0]; // YYYY-MM-DD
        gTime = timestampSec as Time;
      } else if (timeframe === "1M") {
        const year = dateObj.getFullYear();
        const month = dateObj.getMonth();
        groupKey = `${year}-${month}`;
        gTime = timestampSec as Time; // aggregateDailyCandles 에서는 첫날 timestamp 사용
      } else if (timeframe === "1W") {
        const dayOfWeek = dateObj.getDay();
        const diff = dateObj.getDate() - dayOfWeek + (dayOfWeek === 0 ? -6 : 1);
        const monday = new Date(dateObj.setDate(diff));
        monday.setHours(0, 0, 0, 0);
        groupKey = monday.getTime().toString();
        gTime = timestampSec as Time;
      }
    } else {
      const minutes = parseInt(timeframe, 10);
      if (minutes > 1) {
        const intervalSec = minutes * 60;
        const groupTimeSec = Math.floor(timestampSec / intervalSec) * intervalSec;
        groupKey = groupTimeSec.toString();
        gTime = groupTimeSec as Time;
      } else {
        groupKey = timestampSec.toString();
        gTime = timestampSec as Time;
      }
    }

    if (currentGroupKey !== groupKey) {
      if (currentGroupKey !== "" && lastValue !== null && currentGroupTime !== null) {
        result.push({ time: currentGroupTime, value: lastValue });
      }
      currentGroupKey = groupKey;
      currentGroupTime = gTime;
    }
    // 그룹의 마지막 값으로 계속 덮어씀
    lastValue = val;
  }

  // 마지막 꼬리 데이터 밀어넣기
  if (currentGroupKey !== "" && lastValue !== null && currentGroupTime !== null) {
    result.push({ time: currentGroupTime, value: lastValue });
  }

  return result;
}
