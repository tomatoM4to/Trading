from collections import defaultdict, deque


class MACalculator:
    """
    Pandas 의존성 없이 순수 파이썬(Pure Python) Built-in 모듈만을 활용하여
    O(1) 수준의 연산 속도로 2,400개 종목의 이동평균선(MA)을 실시간 갱신하는 엔진입니다.
    """

    def __init__(self, max_period: int = 200):
        self.max_period = max_period
        # 종목코드(ticker)별로 최근 200개의 종가를 담아두는 버퍼
        self.daily_closes: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=max_period)
        )
        self.minute_closes: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=max_period)
        )
        self.ma_periods = (5, 10, 20, 60, 120, 200)

    def add_daily_close(self, ticker: str, close: float) -> None:
        """일봉 종가를 추가합니다."""
        self.daily_closes[ticker].append(close)

    def add_minute_close(self, ticker: str, close: float) -> None:
        """분봉 종가를 추가합니다."""
        self.minute_closes[ticker].append(close)

    def _calculate(self, cache: deque[float]) -> dict[str, float | None]:
        """
        주어진 종가 큐를 기반으로 6개의 고정 이평선(5, 10, 20, 60, 120, 200)을 계산합니다.
        캔들 개수가 부족한(False Positive 방지) 이평선은 None을 반환합니다.
        """
        length = len(cache)
        closes = list(cache)

        result = {}
        for p in self.ma_periods:
            if length < p:
                result[f"ma{p}"] = None
            else:
                # 파이썬 내장 sum()은 C로 최적화되어 있어 매우 빠릅니다.
                # [-p:] 슬라이싱으로 최근 p개 캔들 추출
                ma_value = sum(closes[-p:]) / p
                result[f"ma{p}"] = round(ma_value, 2)
        return result

    def get_daily_ma(self, ticker: str) -> dict[str, float | None]:
        """특정 종목의 최신 일봉 MA 딕셔너리를 반환합니다."""
        return self._calculate(self.daily_closes[ticker])

    def get_minute_ma(self, ticker: str) -> dict[str, float | None]:
        """특정 종목의 최신 분봉 MA 딕셔너리를 반환합니다."""
        return self._calculate(self.minute_closes[ticker])

    def clear(self) -> None:
        """모든 캐시를 초기화합니다 (부트스트랩 용도)."""
        self.daily_closes.clear()
        self.minute_closes.clear()


# 싱글톤 인스턴스 (장중 스케줄러들이 공유)
ma_calculator = MACalculator()
