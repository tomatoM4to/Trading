from typing import Any

from schemas.screener import FilterNode, ScreenerRequest


class ScreenerEngine:
    VALID_MA_PERIODS = {"5", "10", "20", "60", "120", "200"}

    def _validate_ma_line(self, line: str) -> str:
        val = str(line).split("_")[-1]
        if val not in self.VALID_MA_PERIODS:
            raise ValueError(f"유효하지 않은 MA 기간입니다: {line}")
        return f"ma{val}"

    def _validate_duration(self, duration: int, max_val: int = 500) -> int:
        if not isinstance(duration, int) or not (1 <= duration <= max_val):
            raise ValueError(
                f"기간(duration/within)은 1~{max_val} 범위의 정수여야 합니다. (입력: {duration})"
            )
        return duration

    def __init__(self):
        # 지원하는 필터 모듈 맵핑
        self.filter_handlers = {
            "ma_alignment": self._handle_ma_alignment,
            "ma_cross": self._handle_ma_cross,
            "ma_convergence_consolidation": self._handle_ma_convergence_consolidation,
            "ma_convergence_point": self._handle_ma_convergence_point,
            "foreign_net_buy_rank": self._handle_foreign_net_buy_rank,
            "inst_net_buy_rank": self._handle_inst_net_buy_rank,
            "disparity_value": self._handle_disparity_value,
            "volume_peak_breakout": self._handle_volume_peak_breakout,
        }

    def _estimate_cost(self, filter_node: FilterNode) -> float:
        """
        필터의 파라미터를 기반으로 시간복잡도(Big O) O(T * K * L) 형태의 휴리스틱 비용을 계산합니다.
        """
        f_type = filter_node.type
        params = filter_node.params

        # 1. API 기반 필터는 비용 0으로 가장 우선 실행
        if f_type in ("foreign_net_buy_rank", "inst_net_buy_rank"):
            return 0.0

        # 1.5. 단일/서브쿼리 기반 가벼운 필터는 10으로 설정
        if f_type in ("disparity_value", "volume_peak_breakout"):
            return 10.0

        # 2. DB 기반 필터의 K, L 도출

        lines = params.get("lines", [])
        short_line = params.get("short_line")
        long_line = params.get("long_line")

        # Timeframe weight (분봉은 테이블이 훨씬 크므로 3.0의 페널티)
        is_daily = True
        if lines:
            is_daily = any("daily" in line for line in lines)
        elif short_line or long_line:
            is_daily = "daily" in str(short_line) or "daily" in str(long_line)

        table_weight = 1.0 if is_daily else 3.0

        # K (required_rows) 와 L 계산
        if f_type == "ma_alignment" or f_type == "ma_convergence_consolidation":
            duration = params.get("duration", 1)
            k = duration
            line_count = len(lines) if lines else 1
            return float(k * line_count * table_weight)

        elif f_type == "ma_cross":
            within = params.get("within", 1)
            k = within + 1
            line_count = 2
            return float(k * line_count * table_weight)

        elif f_type == "ma_convergence_point":
            within = params.get("within", 1)
            k = within
            line_count = len(lines) if lines else 1
            return float(k * line_count * table_weight)

        return 9999.0

    def _optimize_pipeline(self, request: ScreenerRequest) -> list[list[FilterNode]]:
        """
        요청을 OR 기준으로 여러 AND 체인으로 분할하고,
        각 체인 내의 필터들을 _estimate_cost 비용 오름차순으로 정렬하여 반환합니다.
        """
        if not request.filters:
            return []

        chains = []
        current_chain = [request.filters[0]]

        for i in range(1, len(request.filters)):
            next_filter = request.filters[i]
            operation = request.operations[i - 1]

            if operation == "OR":
                chains.append(current_chain)
                current_chain = [next_filter]
            else:
                current_chain.append(next_filter)

        if current_chain:
            chains.append(current_chain)

        # 각 AND 체인 내부 정렬 (비용 오름차순)
        for chain in chains:
            chain.sort(key=lambda f: self._estimate_cost(f))

        return chains

    async def run_pipeline(
        self, request: ScreenerRequest
    ) -> dict[str, dict[str, float]]:
        """
        주어진 AST 파이프라인을 최적화(분할 및 정렬)한 후 딕셔너리 기반 연산을 수행합니다.
        """
        chains = self._optimize_pipeline(request)
        if not chains:
            return {}

        final_dict = {}

        for chain in chains:
            chain_dict = None

            for filter_node in chain:
                if chain_dict is not None and not chain_dict:
                    break

                result_dict = await self._execute_filter(
                    filter_node, current_tickers=chain_dict
                )

                if chain_dict is None:
                    chain_dict = result_dict
                else:
                    new_dict = {}
                    for ticker, values in chain_dict.items():
                        if ticker in result_dict:
                            new_dict[ticker] = values | result_dict[ticker]
                    chain_dict = new_dict

            if chain_dict:
                for ticker, values in chain_dict.items():
                    if ticker in final_dict:
                        final_dict[ticker] = final_dict[ticker] | values
                    else:
                        final_dict[ticker] = values

        return final_dict

    async def run_pipeline_stream(self, request: ScreenerRequest):
        """
        최적화된 순서대로 파이프라인을 실행하며 SSE 이벤트를 스트리밍합니다.
        """
        import json

        try:
            chains = self._optimize_pipeline(request)
            if not chains:
                yield f"data: {json.dumps({'type': 'complete', 'items': []})}\n\n"
                return

            final_dict = {}

            for chain in chains:
                chain_dict = None

                for filter_node in chain:
                    if chain_dict is not None and not chain_dict:
                        yield f"data: {json.dumps({'type': 'progress', 'filter_id': filter_node.id, 'remaining': 0})}\n\n"
                        continue

                    yield f"data: {json.dumps({'type': 'start', 'filter_id': filter_node.id})}\n\n"

                    result_dict = await self._execute_filter(
                        filter_node, current_tickers=chain_dict
                    )

                    if chain_dict is None:
                        chain_dict = result_dict
                    else:
                        new_dict = {}
                        for ticker, values in chain_dict.items():
                            if ticker in result_dict:
                                new_dict[ticker] = values | result_dict[ticker]
                        chain_dict = new_dict

                    yield f"data: {json.dumps({'type': 'progress', 'filter_id': filter_node.id, 'remaining': len(chain_dict)})}\n\n"

                if chain_dict:
                    for ticker, values in chain_dict.items():
                        if ticker in final_dict:
                            final_dict[ticker] = final_dict[ticker] | values
                        else:
                            final_dict[ticker] = values

            items = self.get_ticker_names(final_dict)
            yield f"data: {json.dumps({'type': 'complete', 'items': items})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    async def _execute_filter(
        self,
        filter_node: FilterNode,
        current_tickers: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, dict[str, float]]:
        """단일 필터 모듈을 호출하여 딕셔너리를 반환합니다."""
        handler = self.filter_handlers.get(filter_node.type)
        if not handler:
            raise ValueError(f"지원하지 않는 필터 타입입니다: {filter_node.type}")
        return await handler(filter_node.id, filter_node.params, current_tickers)

    def get_ticker_names(self, tickers: dict[str, dict[str, float]]) -> list:
        """티커 딕셔너리를 받아 이름과 각종 지표가 포함된 딕셔너리 리스트로 변환합니다."""
        if not tickers:
            return []

        from core.database import connect_sqlite

        conn = connect_sqlite()
        cursor = conn.cursor()
        try:
            placeholders = ",".join("?" for _ in tickers.keys())
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
            cursor.execute(query, tuple(tickers.keys()))
            rows = cursor.fetchall()

            results = []
            for r in rows:
                ticker_code, name, market, market_cap, close, amount, prev_close = r

                change_rate = None
                if close is not None and prev_close is not None and prev_close != 0:
                    change_rate = round((close - prev_close) / prev_close * 100, 2)

                results.append(
                    {
                        "ticker": ticker_code,
                        "name": name,
                        "market": market,
                        "market_cap": market_cap,
                        "close": close,
                        "amount": amount,
                        "change_rate": change_rate,
                        "filter_values": tickers.get(ticker_code, {}),
                    }
                )
            return results
        finally:
            cursor.close()
            conn.close()

    # ==========================================
    # 개별 필터 모듈 로직 (Task 3 에서 구체화 예정)
    # ==========================================

    async def _handle_ma_alignment(
        self,
        filter_id: str,
        params: dict[str, Any],
        current_tickers: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, dict[str, float]]:
        """다중 이평선 정배열 판별 필터 (In-Memory MA 조회)"""
        lines = params.get("lines", [])
        duration = params.get("duration", 1)
        if not lines or len(lines) < 2:
            return {}

        is_daily = any("daily" in line for line in lines)
        table_name = "daily_ma" if is_daily else "minute_ma"
        order_desc = "date DESC" if is_daily else "date DESC, time DESC"

        # 컬럼명 검증 및 매핑
        mapped = [self._validate_ma_line(line) for line in lines]

        max_candles = 390 if not is_daily else 300
        duration = self._validate_duration(duration, max_candles)

        conds = [f"({mapped[i]} > {mapped[i + 1]})" for i in range(len(mapped) - 1)]
        trend_select = (
            f"CASE WHEN {' AND '.join(conds)} THEN 1 ELSE 0 END as is_aligned"
        )
        max_func = f"MAX({', '.join(mapped)})"
        min_func = f"MIN({', '.join(mapped)})"
        val_select = f"(({max_func} - {min_func}) * 100.0 / NULLIF({min_func}, 0)) as alignment_diff"

        from core.database import connect_ma_db, connect_sqlite

        if current_tickers is None:
            conn = connect_sqlite()
            rows = conn.execute(
                "SELECT ticker FROM stock_codes WHERE is_halted=0 AND is_admin_issue=0"
            ).fetchall()
            current_tickers = {r["ticker"]: {} for r in rows}
            conn.close()

        if not current_tickers:
            return {}

        placeholders = ", ".join("?" for _ in current_tickers.keys())
        query_params = tuple(current_tickers.keys())

        query = f"""
        WITH recent_ma AS (
            SELECT * FROM (
                SELECT m.*, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY {order_desc}) as rn
                FROM {table_name} m
                WHERE ticker IN ({placeholders})
            ) WHERE rn <= {duration}
        ),
        trend AS (
            SELECT *, {trend_select}, {val_select} FROM recent_ma
            WHERE {" AND ".join(f"{col} IS NOT NULL" for col in mapped)}
        )
        SELECT ticker, AVG(alignment_diff) as avg_diff FROM trend
        GROUP BY ticker HAVING SUM(is_aligned) = {duration};
        """
        ma_conn = connect_ma_db()
        try:
            return {
                r[0]: {filter_id: round(r[1], 4)}
                for r in ma_conn.execute(query, query_params).fetchall()
            }
        finally:
            ma_conn.close()

    async def _handle_ma_cross(
        self,
        filter_id: str,
        params: dict[str, Any],
        current_tickers: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, dict[str, float]]:
        """이평선 크로스 판별 필터 (In-Memory MA 조회)"""
        short_line = params.get("short_line")
        long_line = params.get("long_line")
        within = params.get("within", 1)
        direction = params.get("direction", "golden")
        if direction not in ("golden", "dead") or not short_line or not long_line:
            return {}

        is_daily = "daily" in short_line or "daily" in long_line
        table_name = "daily_ma" if is_daily else "minute_ma"
        order_desc = "date DESC" if is_daily else "date DESC, time DESC"

        s_col = self._validate_ma_line(short_line)
        l_col = self._validate_ma_line(long_line)

        max_candles = 390 if not is_daily else 300
        within = self._validate_duration(within, max_candles)

        if direction == "golden":
            cross_cond = (
                f"(prev_{s_col} <= prev_{l_col} AND curr_{s_col} > curr_{l_col})"
            )
            cross_val = (
                f"((curr_{s_col} - curr_{l_col}) * 100.0 / NULLIF(curr_{l_col}, 0))"
            )
        else:
            cross_cond = (
                f"(prev_{s_col} >= prev_{l_col} AND curr_{s_col} < curr_{l_col})"
            )
            cross_val = (
                f"((curr_{l_col} - curr_{s_col}) * 100.0 / NULLIF(curr_{s_col}, 0))"
            )

        from core.database import connect_ma_db, connect_sqlite

        if current_tickers is None:
            conn = connect_sqlite()
            rows = conn.execute(
                "SELECT ticker FROM stock_codes WHERE is_halted=0 AND is_admin_issue=0"
            ).fetchall()
            current_tickers = {r["ticker"]: {} for r in rows}
            conn.close()

        if not current_tickers:
            return {}
        placeholders = ", ".join("?" for _ in current_tickers.keys())
        query_params = tuple(current_tickers.keys())

        query = f"""
        WITH recent_ma AS (
            SELECT * FROM (
                SELECT m.*, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY {order_desc}) as rn
                FROM {table_name} m
                WHERE ticker IN ({placeholders})
            ) WHERE rn <= {within + 1}
        ),
        lagged_ma AS (
            SELECT *,
                   {s_col} as curr_{s_col}, {l_col} as curr_{l_col},
                   LEAD({s_col}, 1) OVER(PARTITION BY ticker ORDER BY rn ASC) as prev_{s_col},
                   LEAD({l_col}, 1) OVER(PARTITION BY ticker ORDER BY rn ASC) as prev_{l_col}
            FROM recent_ma
        )
        SELECT ticker, MAX({cross_val}) as cross_diff FROM lagged_ma
        WHERE rn <= {within}
          AND curr_{s_col} IS NOT NULL AND prev_{s_col} IS NOT NULL
          AND curr_{l_col} IS NOT NULL AND prev_{l_col} IS NOT NULL
          AND {cross_cond}
        GROUP BY ticker;
        """
        ma_conn = connect_ma_db()
        try:
            return {
                r[0]: {filter_id: round(r[1], 4)}
                for r in ma_conn.execute(query, query_params).fetchall()
            }
        finally:
            ma_conn.close()

    async def _handle_ma_convergence_consolidation(
        self,
        filter_id: str,
        params: dict[str, Any],
        current_tickers: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, dict[str, float]]:
        """수렴 횡보(상태 유지) 판별 필터 (In-Memory MA 조회)"""
        lines = params.get("lines", [])
        threshold = params.get("threshold", 2.0)
        duration = params.get("duration", 1)
        if not lines or len(lines) < 2:
            return {}

        is_daily = any("daily" in line for line in lines)
        table_name = "daily_ma" if is_daily else "minute_ma"
        order_desc = "date DESC" if is_daily else "date DESC, time DESC"

        mapped = [self._validate_ma_line(line) for line in lines]

        max_candles = 390 if not is_daily else 300
        duration = self._validate_duration(duration, max_candles)

        max_func = f"MAX({', '.join(mapped)})"
        min_func = f"MIN({', '.join(mapped)})"
        diff_val = f"(({max_func} - {min_func}) * 100.0 / NULLIF({min_func}, 0))"
        convergence_cond = f"( {diff_val} <= {threshold} )"
        trend_select = f"CASE WHEN {convergence_cond} THEN 1 ELSE 0 END as is_converged"

        from core.database import connect_ma_db, connect_sqlite

        if current_tickers is None:
            conn = connect_sqlite()
            rows = conn.execute(
                "SELECT ticker FROM stock_codes WHERE is_halted=0 AND is_admin_issue=0"
            ).fetchall()
            current_tickers = {r["ticker"]: {} for r in rows}
            conn.close()

        if not current_tickers:
            return {}
        placeholders = ", ".join("?" for _ in current_tickers.keys())
        query_params = tuple(current_tickers.keys())

        query = f"""
        WITH recent_ma AS (
            SELECT * FROM (
                SELECT m.*, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY {order_desc}) as rn
                FROM {table_name} m
                WHERE ticker IN ({placeholders})
            ) WHERE rn <= {duration}
        ),
        trend AS (
            SELECT *, {trend_select}, {diff_val} as convergence_diff FROM recent_ma
            WHERE {" AND ".join(f"{col} IS NOT NULL" for col in mapped)}
        )
        SELECT ticker, AVG(convergence_diff) as avg_diff FROM trend
        GROUP BY ticker HAVING SUM(is_converged) = {duration};
        """
        ma_conn = connect_ma_db()
        try:
            return {
                r[0]: {filter_id: round(r[1], 4)}
                for r in ma_conn.execute(query, query_params).fetchall()
            }
        finally:
            ma_conn.close()

    async def _handle_ma_convergence_point(
        self,
        filter_id: str,
        params: dict[str, Any],
        current_tickers: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, dict[str, float]]:
        """수렴 지점 발생 판별 필터 (In-Memory MA 조회)"""
        lines = params.get("lines", [])
        threshold = params.get("threshold", 2.0)
        within = params.get("within", 1)
        if not lines or len(lines) < 2:
            return {}

        is_daily = any("daily" in line for line in lines)
        table_name = "daily_ma" if is_daily else "minute_ma"
        order_desc = "date DESC" if is_daily else "date DESC, time DESC"

        mapped = [self._validate_ma_line(line) for line in lines]

        max_candles = 390 if not is_daily else 300
        within = self._validate_duration(within, max_candles)

        max_func = f"MAX({', '.join(mapped)})"
        min_func = f"MIN({', '.join(mapped)})"
        diff_val = f"(({max_func} - {min_func}) * 100.0 / NULLIF({min_func}, 0))"
        convergence_cond = f"( {diff_val} <= {threshold} )"
        trend_select = f"CASE WHEN {convergence_cond} THEN 1 ELSE 0 END as is_converged"

        from core.database import connect_ma_db, connect_sqlite

        if current_tickers is None:
            conn = connect_sqlite()
            rows = conn.execute(
                "SELECT ticker FROM stock_codes WHERE is_halted=0 AND is_admin_issue=0"
            ).fetchall()
            current_tickers = {r["ticker"]: {} for r in rows}
            conn.close()

        if not current_tickers:
            return {}
        placeholders = ", ".join("?" for _ in current_tickers.keys())
        query_params = tuple(current_tickers.keys())

        query = f"""
        WITH recent_ma AS (
            SELECT * FROM (
                SELECT m.*, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY {order_desc}) as rn
                FROM {table_name} m
                WHERE ticker IN ({placeholders})
            ) WHERE rn <= {within}
        ),
        trend AS (
            SELECT *, {trend_select}, {diff_val} as convergence_diff FROM recent_ma
            WHERE {" AND ".join(f"{col} IS NOT NULL" for col in mapped)}
        )
        SELECT ticker, MIN(convergence_diff) as min_diff FROM trend
        WHERE is_converged = 1
        GROUP BY ticker;
        """
        ma_conn = connect_ma_db()
        try:
            return {
                r[0]: {filter_id: round(r[1], 4)}
                for r in ma_conn.execute(query, query_params).fetchall()
            }
        finally:
            ma_conn.close()

    async def _handle_disparity_value(
        self,
        filter_id: str,
        params: dict[str, Any],
        current_tickers: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, dict[str, float]]:
        """이격도 판별 필터 (ATTACH DATABASE 활용)"""
        line = params.get("line")
        threshold = params.get("threshold")
        direction = params.get("direction")

        if not line or threshold is None or direction not in ("above", "below"):
            raise ValueError(
                f"disparity_value 파라미터 오류: line, threshold, direction(above/below) 필수. (입력: {params})"
            )

        valid_line = self._validate_ma_line(line)
        operator = "<=" if direction == "below" else ">="
        threshold = float(threshold)

        is_daily = "daily" in valid_line
        main_table = "daily_ohlcv" if is_daily else "minute_ohlcv"
        ma_table = "daily_ma" if is_daily else "minute_ma"
        order_desc = "date DESC" if is_daily else "date DESC, time DESC"

        from core.database import _MA_MEM_DB_URI, connect_sqlite

        if current_tickers is None:
            conn = connect_sqlite()
            try:
                rows = conn.execute(
                    "SELECT ticker FROM stock_codes WHERE is_halted=0 AND is_admin_issue=0"
                ).fetchall()
                current_tickers = {r["ticker"]: {} for r in rows}
            finally:
                conn.close()

        if not current_tickers:
            return {}

        conn = connect_sqlite()
        try:
            conn.execute(f"ATTACH DATABASE '{_MA_MEM_DB_URI}' AS madb")

            placeholders = ", ".join("?" for _ in current_tickers.keys())
            query_params = list(current_tickers.keys())
            query_params.extend(current_tickers.keys())
            query_params.append(threshold)

            query = f"""
            WITH latest_main AS (
                SELECT ticker, close
                FROM (
                    SELECT ticker, close,
                           ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY {order_desc}) as rn
                    FROM {main_table}
                    WHERE ticker IN ({placeholders})
                ) WHERE rn = 1
            ),
            latest_ma AS (
                SELECT ticker, {valid_line}
                FROM (
                    SELECT ticker, {valid_line},
                           ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY {order_desc}) as rn
                    FROM madb.{ma_table}
                    WHERE ticker IN ({placeholders})
                ) WHERE rn = 1
            )
            SELECT d.ticker, (CAST(d.close AS REAL) / NULLIF(m.{valid_line}, 0)) * 100.0 as disparity
            FROM latest_main d
            JOIN latest_ma m ON d.ticker = m.ticker
            WHERE m.{valid_line} IS NOT NULL
              AND (CAST(d.close AS REAL) / NULLIF(m.{valid_line}, 0)) * 100.0 {operator} ?
            """

            return {
                r["ticker"]: {filter_id: round(r["disparity"], 4)}
                for r in conn.execute(query, query_params).fetchall()
            }
        finally:
            try:
                conn.execute("DETACH DATABASE madb")
            except Exception:
                pass
            conn.close()

    async def _handle_volume_peak_breakout(
        self,
        filter_id: str,
        params: dict[str, Any],
        current_tickers: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, dict[str, float]]:
        """최대 거래량 매물대 돌파 판별 필터"""
        lookback = params.get("lookback")
        if lookback not in ("1M", "3M", "2H", "4H"):
            raise ValueError(
                f"volume_peak_breakout 파라미터 오류: lookback은 '1M', '3M', '2H', '4H' 중 하나여야 합니다. (입력: {lookback})"
            )

        is_daily = "M" in lookback
        table_name = "daily_ohlcv" if is_daily else "minute_ohlcv"
        order_desc = "date DESC" if is_daily else "date DESC, time DESC"

        duration = {"1M": 30, "3M": 60, "2H": 120, "4H": 240}[lookback]

        from core.database import connect_sqlite

        if current_tickers is None:
            conn = connect_sqlite()
            try:
                rows = conn.execute(
                    "SELECT ticker FROM stock_codes WHERE is_halted=0 AND is_admin_issue=0"
                ).fetchall()
                current_tickers = {r["ticker"]: {} for r in rows}
            finally:
                conn.close()

        if not current_tickers:
            return {}

        conn = connect_sqlite()
        try:
            placeholders = ", ".join("?" for _ in current_tickers.keys())
            query_params = tuple(current_tickers.keys())

            query = f"""
            WITH recent_data AS (
                SELECT ticker, close, high, volume, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY {order_desc}) as rn
                FROM {table_name}
                WHERE ticker IN ({placeholders})
            ),
            latest_close AS (
                SELECT ticker, close
                FROM recent_data
                WHERE rn = 1
            ),
            max_volume_candle AS (
                SELECT ticker, high as max_vol_high
                FROM (
                    SELECT ticker, high, ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY volume DESC) as v_rn
                    FROM recent_data
                    WHERE rn <= {duration}
                ) WHERE v_rn = 1
            )
            SELECT l.ticker, ((l.close - m.max_vol_high) * 100.0 / NULLIF(m.max_vol_high, 0)) as breakout_rate
            FROM latest_close l
            JOIN max_volume_candle m ON l.ticker = m.ticker
            WHERE l.close > m.max_vol_high
            """

            return {
                r["ticker"]: {filter_id: round(r["breakout_rate"], 4)}
                for r in conn.execute(query, query_params).fetchall()
            }
        finally:
            conn.close()

    async def _fetch_investor_rank(
        self, etc_cls_code: str, filter_id: str, limit: int = 30
    ) -> dict[str, dict[str, float]]:
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
            "FID_ETC_CLS_CODE": etc_cls_code,
        }

        # 첫 번째 페이지 조회 (최대 30건)
        res = await async_kis_fetch(
            api_url="/uapi/domestic-stock/v1/quotations/foreign-institution-total",
            ptr_id="FHPTJ04400000",
            tr_cont="",
            params=params,
            priority=5,
        )

        if res.is_ok():
            body = res.get_body()
            output = getattr(body, "output", []) or []

            for item in output:
                ticker = item.get("mksc_shrn_iscd") or item.get("stck_shrn_iscd")
                if ticker:
                    tickers.append(ticker)

            unique_tickers = []
            for t in tickers:
                if t not in unique_tickers:
                    unique_tickers.append(t)

            # API 반환 순서대로 1.0, 2.0... 의 순위(Float)를 부여
            return {
                t: {filter_id: float(i + 1)}
                for i, t in enumerate(unique_tickers[:limit])
            }
        return {}

    async def _handle_foreign_net_buy_rank(
        self,
        filter_id: str,
        params: dict[str, Any],
        current_tickers: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, dict[str, float]]:
        """외국인 순매수 상위 필터"""
        limit = params.get("limit", 30)
        res = await self._fetch_investor_rank(
            etc_cls_code="1", filter_id=filter_id, limit=limit
        )
        if current_tickers is not None:
            return {t: res[t] for t in res if t in current_tickers}
        return res

    async def _handle_inst_net_buy_rank(
        self,
        filter_id: str,
        params: dict[str, Any],
        current_tickers: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, dict[str, float]]:
        """기관 순매수 상위 필터"""
        limit = params.get("limit", 30)
        res = await self._fetch_investor_rank(
            etc_cls_code="2", filter_id=filter_id, limit=limit
        )
        if current_tickers is not None:
            return {t: res[t] for t in res if t in current_tickers}
        return res


screener_engine = ScreenerEngine()
