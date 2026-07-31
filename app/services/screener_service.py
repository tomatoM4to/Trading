from typing import Any

from schemas.screener import FilterNode, ScreenerRequest


class ScreenerEngine:
    def __init__(self):
        # 지원하는 필터 모듈 맵핑
        self.filter_handlers = {
            "ma_uptrend": self._handle_ma_uptrend,
            "convergence": self._handle_convergence,
            "foreign_buy": self._handle_foreign_buy,
        }

    async def run_pipeline(self, request: ScreenerRequest) -> set[str]:
        """
        주어진 AST(플랫 리스트) 파이프라인을 순회하며 Set 연산을 수행합니다.
        """
        if not request.filters:
            return set()

        # 1. 첫 번째 필터 실행하여 초기 기준 집합 생성
        first_filter = request.filters[0]
        current_set = await self._execute_filter(first_filter)

        # 2. 두 번째 필터부터 순차적으로 파이프라인(AND/OR) 연산 수행
        for i in range(1, len(request.filters)):
            next_filter = request.filters[i]
            operation = request.operations[i - 1]  # 현재 필터와 직전 결과 사이의 연산자

            # 다음 필터 실행 (지연 평가 - 나중에 최적화 시 이 시점에서 AND 연산일 경우 current_set을 넘겨 쿼리를 제한할 수도 있음)
            next_set = await self._execute_filter(next_filter)

            # 집합 연산
            if operation == "AND":
                current_set = current_set & next_set
            elif operation == "OR":
                current_set = current_set | next_set

        return current_set

    async def _execute_filter(self, filter_node: FilterNode) -> set[str]:
        """단일 필터 모듈을 호출하여 티커 집합(Set)을 반환합니다."""
        handler = self.filter_handlers.get(filter_node.type)
        if not handler:
            raise ValueError(f"지원하지 않는 필터 타입입니다: {filter_node.type}")
        return await handler(filter_node.params)

    def get_ticker_names(self, tickers: set[str]) -> list:
        """티커 Set을 받아 이름이 포함된 딕셔너리 리스트로 변환합니다."""
        if not tickers:
            return []

        from core.database import connect_sqlite

        conn = connect_sqlite()
        cursor = conn.cursor()
        try:
            placeholders = ",".join("?" for _ in tickers)
            cursor.execute(
                f"SELECT ticker, name FROM stock_codes WHERE ticker IN ({placeholders})",
                tuple(tickers),
            )
            rows = cursor.fetchall()
            return [{"ticker": r[0], "name": r[1]} for r in rows]
        finally:
            cursor.close()
            conn.close()

    # ==========================================
    # 개별 필터 모듈 로직 (Task 3 에서 구체화 예정)
    # ==========================================

    async def _handle_ma_uptrend(self, params: dict[str, Any]) -> set[str]:
        """다중 이평선 우상향 판별 필터 (SQLite Push-down)"""
        lines = params.get("lines", [])
        days = params.get("days", 1)
        if not lines:
            return set()

        # 1. 이평선 윈도우 크기 맵핑
        windows = {
            "ma_daily_5": 4,
            "ma_daily_20": 19,
            "ma_daily_60": 59,
            "ma_daily_120": 119,
            "ma5": 4,
            "ma10": 9,
            "ma20": 19,
            "ma60": 59,
            "ma120": 119,
        }

        is_daily = any("daily" in ma_line for ma_line in lines)
        table_name = "daily_ohlcv" if is_daily else "minute_ohlcv"
        order_clause = "date ASC" if is_daily else "date ASC, time ASC"
        order_desc_clause = "date DESC" if is_daily else "date DESC, time DESC"

        # 2. 가장 긴 이평선에 맞춰 필요한 최근 N개의 Row 수 계산
        max_window = max(windows.get(ma_line, 0) for ma_line in lines)
        required_rows = max_window + days + 1

        # 3. SELECT 구문 동적 생성
        ma_selects = []
        trend_selects = []
        having_clauses = []

        for ma_line in lines:
            w = windows.get(ma_line, 0)
            ma_selects.append(
                f"CASE WHEN COUNT(close) OVER(PARTITION BY ticker ORDER BY {order_clause} ROWS BETWEEN {w} PRECEDING AND CURRENT ROW) = {w + 1} "
                f"THEN AVG(close) OVER(PARTITION BY ticker ORDER BY {order_clause} ROWS BETWEEN {w} PRECEDING AND CURRENT ROW) "
                f"ELSE NULL END as {ma_line}"
            )
            trend_selects.append(
                f"({ma_line} > LAG({ma_line}, 1) OVER(PARTITION BY ticker ORDER BY {order_clause})) as {ma_line}_up"
            )
            having_clauses.append(f"SUM({ma_line}_up) = {days}")

        ma_select_str = ",\n                ".join(ma_selects)
        trend_select_str = ",\n                ".join(trend_selects)
        having_str = " AND ".join(having_clauses)

        query = f"""
        WITH recent_data AS (
            SELECT * FROM (
                SELECT *,
                       ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY {order_desc_clause}) as rn
                FROM {table_name}
            ) WHERE rn <= {required_rows}
        ),
        calc_ma AS (
            SELECT
                *,
                {ma_select_str}
            FROM recent_data
        ),
        trend AS (
            SELECT
                *,
                {trend_select_str}
            FROM calc_ma
        )
        SELECT ticker
        FROM trend
        WHERE rn <= {days}
        GROUP BY ticker
        HAVING {having_str};
        """

        from core.database import connect_sqlite

        conn = connect_sqlite()
        cursor = conn.cursor()
        try:
            cursor.execute(query)
            rows = cursor.fetchall()
            return {r[0] for r in rows}
        finally:
            cursor.close()
            conn.close()

    async def _handle_convergence(self, params: dict[str, Any]) -> set[str]:
        """이평선 수렴 판별 필터 (SQLite)"""
        return set()

    async def _handle_foreign_buy(self, params: dict[str, Any]) -> set[str]:
        """외국인 순매수 필터 (KIS API)"""
        return set()


screener_engine = ScreenerEngine()
