# Spec: 이격도 및 매물대(Max Volume) 스크리너 필터 추가

## 1. Objective (목적)
- **무엇을**: 1 OCPU/1GB RAM 서버 환경의 메모리/디스크 부하를 유발하지 않으면서, 실시간 스크리너 엔진에 `disparity_value`(이격도)와 `volume_peak_breakout`(최대 거래량 캔들 돌파) 필터를 추가합니다.
- **왜**: 실전 트레이딩에서 가장 승률이 높은 '과대낙폭 반등' 및 '주요 악성 매물대 소화 후 슈팅' 타점을 잡기 위함입니다.
- **성공 기준 (Success Criteria)**:
  - 두 필터를 동시 적용하여 스크리너(`POST /api/screener/run`)를 호출했을 때 타임아웃(60초) 없이 정상적으로 SSE 응답이 스트리밍 되어야 합니다.
  - 두 필터 연산 시 추가적인 디스크 I/O나 파일 잠금(Lock) 에러가 발생하지 않아야 합니다. (100% In-Memory 연산)

## 2. Tech Stack & Commands
- **환경**: FastAPI, SQLite (In-Memory `file::memory:?cache=shared`), Python 3.12
- **Commands**:
  - 실행: `uv run fastapi dev app/main.py`
  - 린트/포맷: `uv run ruff check . --fix && uv run ruff format .`
  - 테스트: `uv run pytest -v`

## 3. Project Structure (영향도)
이번 피처 개발로 인해 수정될 핵심 파일들입니다:
- `app/services/screener_service.py`: SQLite 쿼리를 동적으로 생성하는 `ScreenerEngine`에 두 가지 신규 필터 파서(AST 변환 로직) 추가.
  - `_handle_disparity_value`: `ATTACH DATABASE`를 활용하여 `daily_ohlcv`의 종가(close)와 `madb.daily_ma`의 이동평균선을 JOIN하여 이격도를 계산.
  - `_handle_volume_peak_breakout`: 지정된 고정 기간 내 최대 거래량(`ORDER BY volume DESC LIMIT 1`) 캔들의 고가(High)를 찾아 돌파 여부 판별.
- `docs/screener.md`: 신규 필터 2종에 대한 API 파라미터 명세서 업데이트.

## 4. Code Style
- **보안 및 인젝션 방어**: ADR-033에 따라, 클라이언트가 보낸 이평선 이름(`line`)과 고정 프리셋(`lookback`)은 반드시 화이트리스트 딕셔너리나 Set을 통해 검증한 후 SQL 문자열에 바인딩합니다.
- **예시 (이격도 방어)**:
  ```python
  # BAD: 
  f"({close_col} / {line}) * 100 <= {threshold}"
  
  # GOOD: 
  valid_line = self._validate_ma_line(line)
  operator = "<=" if direction == "below" else ">="
  return f"(close / {valid_line}) * 100 {operator} ?", (threshold,)
  ```

## 5. Testing Strategy
- 운영 DB 오염을 막기 위해 `test_trading.db`로 라우팅하는 컨텍스트(ADR-023) 위에서 테스트합니다.
- 악의적인 파라미터(예: `lookback="DROP TABLE"`)가 주입되었을 때 정확히 `ValueError`가 발생하는지 단위 테스트로 검증합니다.

## 6. Boundaries
- **Always do**: 파라미터를 SQL로 변환하기 전 엄격한 화이트리스트 검증(Anti-Short-Circuit) 수행.
- **Ask first**: SQLite 인메모리 테이블 구조나 컬럼을 변경해야 하는 상황이 발생할 경우.
- **Never do**: 캔들 반복문을 돌며 파이썬 딕셔너리나 리스트 상에서 매물대를 직접 계산하는 행위 (반드시 SQLite 서브쿼리 위임 푸시다운 적용).
