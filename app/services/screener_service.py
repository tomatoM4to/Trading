from typing import Any

from schemas.screener import FilterNode, ScreenerRequest


class ScreenerEngine:
    def __init__(self):
        # 지원하는 필터 모듈 맵핑
        self.filter_handlers = {
            "ma_alignment": self._handle_ma_alignment,
            "ma_cross": self._handle_ma_cross,
            "ma_convergence_consolidation": self._handle_ma_convergence_consolidation,
            "ma_convergence_point": self._handle_ma_convergence_point,
            "foreign_net_buy_rank": self._handle_foreign_net_buy_rank,
            "inst_net_buy_rank": self._handle_inst_net_buy_rank,
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

    async def run_pipeline_stream(self, request: ScreenerRequest):
        """
        주어진 AST(플랫 리스트) 파이프라인을 순회하며 Set 연산을 수행하고 SSE 이벤트를 스트리밍합니다.
        """
        import json
        if not request.filters:
            yield f"data: {json.dumps({'type': 'complete', 'items': []})}\n\n"
            return

        # 1. 첫 번째 필터 실행
        first_filter = request.filters[0]
        current_set = await self._execute_filter(first_filter)
        
        # 첫 번째 필터 종료 이벤트 yield
        yield f"data: {json.dumps({'type': 'progress', 'filter_id': first_filter.id, 'remaining': len(current_set)})}\n\n"

        # 2. 두 번째 필터부터 순차 연산
        for i in range(1, len(request.filters)):
            next_filter = request.filters[i]
            operation = request.operations[i - 1]

            next_set = await self._execute_filter(next_filter)

            if operation == "AND":
                current_set = current_set & next_set
            elif operation == "OR":
                current_set = current_set | next_set

            yield f"data: {json.dumps({'type': 'progress', 'filter_id': next_filter.id, 'remaining': len(current_set)})}\n\n"

        # 3. 최종 결과 확장(Enrichment)
        items = self.get_ticker_names(current_set)
        
        # 최종 완료 이벤트 yield
        yield f"data: {json.dumps({'type': 'complete', 'items': items})}\n\n"

    async def _execute_filter(self, filter_node: FilterNode) -> set[str]:
        """단일 필터 모듈을 호출하여 티커 집합(Set)을 반환합니다."""
        handler = self.filter_handlers.get(filter_node.type)
        if not handler:
            raise ValueError(f"지원하지 않는 필터 타입입니다: {filter_node.type}")
        return await handler(filter_node.params)

    def get_ticker_names(self, tickers: set[str]) -> list:
        """티커 Set을 받아 이름과 각종 지표가 포함된 딕셔너리 리스트로 변환합니다."""
        if not tickers:
            return []

        from core.database import connect_sqlite

        conn = connect_sqlite()
        cursor = conn.cursor()
        try:
            placeholders = ",".join("?" for _ in tickers)
            query = f"""
            SELECT 
                s.ticker, 
                s.name, 
                s.market, 
                s.market_cap,
                (SELECT close FROM minute_ohlcv m WHERE m.ticker = s.ticker ORDER BY date DESC, time DESC LIMIT 1) as close,
                (SELECT amount FROM minute_ohlcv m WHERE m.ticker = s.ticker ORDER BY date DESC, time DESC LIMIT 1) as amount,
                (
                    SELECT d.close 
                    FROM daily_ohlcv d 
                    WHERE d.ticker = s.ticker 
                      AND d.date < (SELECT m2.date FROM minute_ohlcv m2 WHERE m2.ticker = s.ticker ORDER BY m2.date DESC LIMIT 1)
                    ORDER BY d.date DESC 
                    LIMIT 1
                ) as prev_close
            FROM stock_codes s
            WHERE s.ticker IN ({placeholders})
            """
            cursor.execute(query, tuple(tickers))
            rows = cursor.fetchall()
            
            results = []
            for r in rows:
                ticker, name, market, market_cap, close, amount, prev_close = r
                
                change_rate = None
                if close is not None and prev_close is not None and prev_close != 0:
                    change_rate = round((close - prev_close) / prev_close * 100, 2)
                    
                results.append({
                    "ticker": ticker,
                    "name": name,
                    "market": market,
                    "market_cap": market_cap,
                    "close": close,
                    "amount": amount,
                    "change_rate": change_rate
                })
            return results
        finally:
            cursor.close()
            conn.close()

    # ==========================================
    # 개별 필터 모듈 로직 (Task 3 에서 구체화 예정)
    # ==========================================

    async def _handle_ma_alignment(self, params: dict[str, Any]) -> set[str]:
        """다중 이평선 정배열(상태) 판별 필터 (SQLite Push-down)"""
        lines = params.get("lines", [])
        duration = params.get("duration", 1)
        if not lines or len(lines) < 2:
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

        # 2. 파라미터 유효성 검사 (GC 방어)
        max_candles = 200 if is_daily else 1950
        max_window = max(windows.get(ma_line, 0) for ma_line in lines)
        if duration > max_candles - max_window - 1:
            raise ValueError(f"지정된 duration({duration})이 GC 보관 주기를 초과하여 쿼리할 수 없습니다.")

        required_rows = max_window + duration + 1

        # 3. SELECT 구문 동적 생성
        ma_selects = []
        for ma_line in lines:
            w = windows.get(ma_line, 0)
            ma_selects.append(
                f"CASE WHEN COUNT(close) OVER(PARTITION BY ticker ORDER BY {order_clause} ROWS BETWEEN {w} PRECEDING AND CURRENT ROW) = {w + 1} "
                f"THEN AVG(close) OVER(PARTITION BY ticker ORDER BY {order_clause} ROWS BETWEEN {w} PRECEDING AND CURRENT ROW) "
                f"ELSE NULL END as {ma_line}"
            )
        
        # 배열의 순서대로 크기 비교 (lines[0] > lines[1] > lines[2] ...)
        alignment_conditions = [f"({lines[i]} > {lines[i+1]})" for i in range(len(lines) - 1)]
        alignment_cond_str = " AND ".join(alignment_conditions)
        trend_select = f"CASE WHEN {alignment_cond_str} THEN 1 ELSE 0 END as is_aligned"

        ma_select_str = ",\n                ".join(ma_selects)

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
                {trend_select}
            FROM calc_ma
        )
        SELECT ticker
        FROM trend
        WHERE rn <= {duration}
        GROUP BY ticker
        HAVING SUM(is_aligned) = {duration};
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

    async def _handle_ma_cross(self, params: dict[str, Any]) -> set[str]:
        """이평선 크로스(이벤트) 판별 필터 (SQLite Push-down)"""
        short_line = params.get("short_line")
        long_line = params.get("long_line")
        within = params.get("within", 1)
        direction = params.get("direction", "golden") # "golden" or "dead"

        if not short_line or not long_line:
            return set()
            
        windows = {
            "ma_daily_5": 4, "ma_daily_20": 19, "ma_daily_60": 59, "ma_daily_120": 119,
            "ma5": 4, "ma10": 9, "ma20": 19, "ma60": 59, "ma120": 119,
        }

        is_daily = "daily" in short_line or "daily" in long_line
        table_name = "daily_ohlcv" if is_daily else "minute_ohlcv"
        order_clause = "date ASC" if is_daily else "date ASC, time ASC"
        order_desc_clause = "date DESC" if is_daily else "date DESC, time DESC"

        # GC 방어 유효성 검사
        max_candles = 200 if is_daily else 1950
        w_short = windows.get(short_line, 0)
        w_long = windows.get(long_line, 0)
        max_window = max(w_short, w_long)
        
        if within > max_candles - max_window - 1:
            raise ValueError(f"지정된 within({within})이 GC 보관 주기를 초과합니다.")

        required_rows = max_window + within + 2  # +2 for LAG

        ma_selects = []
        for ma_line, w in [(short_line, w_short), (long_line, w_long)]:
            ma_selects.append(
                f"CASE WHEN COUNT(close) OVER(PARTITION BY ticker ORDER BY {order_clause} ROWS BETWEEN {w} PRECEDING AND CURRENT ROW) = {w + 1} "
                f"THEN AVG(close) OVER(PARTITION BY ticker ORDER BY {order_clause} ROWS BETWEEN {w} PRECEDING AND CURRENT ROW) "
                f"ELSE NULL END as {ma_line}"
            )
        
        ma_select_str = ",\n                ".join(ma_selects)
        
        cross_cond = "1=0"
        if direction == "golden":
            cross_cond = f"(prev_{short_line} <= prev_{long_line} AND curr_{short_line} > curr_{long_line})"
        elif direction == "dead":
            cross_cond = f"(prev_{short_line} >= prev_{long_line} AND curr_{short_line} < curr_{long_line})"

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
        lagged_ma AS (
            SELECT
                *,
                {short_line} as curr_{short_line},
                {long_line} as curr_{long_line},
                LAG({short_line}, 1) OVER(PARTITION BY ticker ORDER BY {order_clause}) as prev_{short_line},
                LAG({long_line}, 1) OVER(PARTITION BY ticker ORDER BY {order_clause}) as prev_{long_line}
            FROM calc_ma
        )
        SELECT ticker
        FROM lagged_ma
        WHERE rn <= {within}
          AND curr_{short_line} IS NOT NULL
          AND prev_{short_line} IS NOT NULL
          AND curr_{long_line} IS NOT NULL
          AND prev_{long_line} IS NOT NULL
          AND {cross_cond}
        GROUP BY ticker;
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

    async def _handle_ma_convergence_consolidation(self, params: dict[str, Any]) -> set[str]:
        """수렴 횡보(상태 유지) 판별 필터"""
        lines = params.get("lines", [])
        threshold = params.get("threshold", 2.0)
        duration = params.get("duration", 1)

        if not lines or len(lines) < 2:
            return set()

        windows = {
            "ma_daily_5": 4, "ma_daily_20": 19, "ma_daily_60": 59, "ma_daily_120": 119,
            "ma5": 4, "ma10": 9, "ma20": 19, "ma60": 59, "ma120": 119,
        }

        is_daily = any("daily" in ma_line for ma_line in lines)
        table_name = "daily_ohlcv" if is_daily else "minute_ohlcv"
        order_clause = "date ASC" if is_daily else "date ASC, time ASC"
        order_desc_clause = "date DESC" if is_daily else "date DESC, time DESC"

        max_candles = 200 if is_daily else 1950
        max_window = max(windows.get(ma_line, 0) for ma_line in lines)
        if duration > max_candles - max_window - 1:
            raise ValueError(f"지정된 duration({duration})이 GC 보관 주기를 초과합니다.")

        required_rows = max_window + duration + 1

        ma_selects = []
        for ma_line in lines:
            w = windows.get(ma_line, 0)
            ma_selects.append(
                f"CASE WHEN COUNT(close) OVER(PARTITION BY ticker ORDER BY {order_clause} ROWS BETWEEN {w} PRECEDING AND CURRENT ROW) = {w + 1} "
                f"THEN AVG(close) OVER(PARTITION BY ticker ORDER BY {order_clause} ROWS BETWEEN {w} PRECEDING AND CURRENT ROW) "
                f"ELSE NULL END as {ma_line}"
            )
        
        ma_select_str = ",\n                ".join(ma_selects)
        
        max_func = f"MAX({', '.join(lines)})"
        min_func = f"MIN({', '.join(lines)})"
        
        convergence_cond = f"( ({max_func} - {min_func}) * 1.0 / NULLIF({min_func}, 0) <= {threshold / 100.0} )"
        trend_select = f"CASE WHEN {convergence_cond} THEN 1 ELSE 0 END as is_converged"

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
                {trend_select}
            FROM calc_ma
            WHERE {' AND '.join(f'{line} IS NOT NULL' for line in lines)}
        )
        SELECT ticker
        FROM trend
        WHERE rn <= {duration}
        GROUP BY ticker
        HAVING SUM(is_converged) = {duration};
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

    async def _handle_ma_convergence_point(self, params: dict[str, Any]) -> set[str]:
        """수렴 지점(이벤트 발생) 판별 필터"""
        lines = params.get("lines", [])
        threshold = params.get("threshold", 2.0)
        within = params.get("within", 1)

        if not lines or len(lines) < 2:
            return set()

        windows = {
            "ma_daily_5": 4, "ma_daily_20": 19, "ma_daily_60": 59, "ma_daily_120": 119,
            "ma5": 4, "ma10": 9, "ma20": 19, "ma60": 59, "ma120": 119,
        }

        is_daily = any("daily" in ma_line for ma_line in lines)
        table_name = "daily_ohlcv" if is_daily else "minute_ohlcv"
        order_clause = "date ASC" if is_daily else "date ASC, time ASC"
        order_desc_clause = "date DESC" if is_daily else "date DESC, time DESC"

        max_candles = 200 if is_daily else 1950
        max_window = max(windows.get(ma_line, 0) for ma_line in lines)
        if within > max_candles - max_window - 1:
            raise ValueError(f"지정된 within({within})이 GC 보관 주기를 초과합니다.")

        required_rows = max_window + within + 1

        ma_selects = []
        for ma_line in lines:
            w = windows.get(ma_line, 0)
            ma_selects.append(
                f"CASE WHEN COUNT(close) OVER(PARTITION BY ticker ORDER BY {order_clause} ROWS BETWEEN {w} PRECEDING AND CURRENT ROW) = {w + 1} "
                f"THEN AVG(close) OVER(PARTITION BY ticker ORDER BY {order_clause} ROWS BETWEEN {w} PRECEDING AND CURRENT ROW) "
                f"ELSE NULL END as {ma_line}"
            )
        
        ma_select_str = ",\n                ".join(ma_selects)
        
        max_func = f"MAX({', '.join(lines)})"
        min_func = f"MIN({', '.join(lines)})"
        
        convergence_cond = f"( ({max_func} - {min_func}) * 1.0 / NULLIF({min_func}, 0) <= {threshold / 100.0} )"
        trend_select = f"CASE WHEN {convergence_cond} THEN 1 ELSE 0 END as is_converged"

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
                {trend_select}
            FROM calc_ma
            WHERE {' AND '.join(f'{line} IS NOT NULL' for line in lines)}
        )
        SELECT ticker
        FROM trend
        WHERE rn <= {within}
          AND is_converged = 1
        GROUP BY ticker;
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

    async def _fetch_investor_rank(self, etc_cls_code: str, limit: int = 30) -> set[str]:
        """
        KIS OpenAPI (FHPTJ04400000) 가집계 랭킹 API 호출.
        etc_cls_code: "1" (외국인), "2" (기관계)
        """
        from core.kis_fetch import async_kis_fetch
        
        tickers = []
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "V",
            "FID_COND_SCR_DIV_CODE": "16449",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",  # 0: 수량정렬
            "FID_RANK_SORT_CLS_CODE": "0",  # 0: 순매수상위
            "FID_ETC_CLS_CODE": etc_cls_code
        }
        
        # 첫 번째 페이지 조회 (최대 30건)
        res = await async_kis_fetch(
            api_url="/uapi/domestic-stock/v1/quotations/foreign-institution-total",
            ptr_id="FHPTJ04400000",
            tr_cont="",
            params=params,
            priority=5
        )
        
        if res.is_ok():
            body = res.get_body()
            output = getattr(body, "output", []) or []
            
            for item in output:
                ticker = item.get("mksc_shrn_iscd") or item.get("stck_shrn_iscd")
                if ticker:
                    tickers.append(ticker)
            
            # KIS API "국내기관_외국인 매매종목가집계"는 상위 30건으로 고정되어 있으며 연속조회를 지원하지 않습니다.
            # 중복 제거 후 반환 (단일 호출로 30건)
            unique_tickers = []
            for t in tickers:
                if t not in unique_tickers:
                    unique_tickers.append(t)
                    
            return set(unique_tickers[:limit])

    async def _handle_foreign_net_buy_rank(self, params: dict[str, Any]) -> set[str]:
        """외국인 순매수 상위 필터"""
        limit = params.get("limit", 30)
        return await self._fetch_investor_rank(etc_cls_code="1", limit=limit)

    async def _handle_inst_net_buy_rank(self, params: dict[str, Any]) -> set[str]:
        """기관 순매수 상위 필터"""
        limit = params.get("limit", 30)
        return await self._fetch_investor_rank(etc_cls_code="2", limit=limit)


screener_engine = ScreenerEngine()
