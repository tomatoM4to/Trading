# Plan: 이격도 및 매물대(Max Volume) 스크리너 필터 추가

## 1. 개요
스크리너 파이프라인에 2개의 신규 원자적 필터(`disparity_value`, `volume_peak_breakout`)를 추가합니다. `ScreenerEngine` 내부에 처리 핸들러를 추가하고, `screener.md` 명세서를 업데이트합니다.

## 2. 구현 순서 (Implementation Order)
1. **명세서 업데이트 (`docs/screener.md`)**
   - 클라이언트(프론트엔드) 연동을 위해 2개의 신규 필터에 대한 요청 스키마(파라미터 형태 및 프리셋 제약)를 명확히 작성합니다.
2. **`ScreenerEngine` 신규 필터 등록 (`screener_service.py`)**
   - `__init__` 메서드의 `filter_handlers` 맵에 `"disparity_value"`와 `"volume_peak_breakout"`를 추가합니다.
   - `_estimate_cost` 맵에 두 필터의 쿼리 코스트를 할당합니다. (모두 단일/서브쿼리 인메모리 연산이므로 기본 비용 10으로 설정).
3. **`_handle_disparity_value` 구현**
   - 파라미터 검증 (`line`, `direction`, `threshold`).
   - SQLite `ATTACH DATABASE`를 이용하여 메인 DB와 MA DB를 조인.
   - `(d.close / m.ma_line) * 100` 수식을 사용하여 조건에 부합하는 티커와 해당 이격도 값을 추출.
4. **`_handle_volume_peak_breakout` 구현**
   - 프리셋 기간(`1M`, `3M`, `2H`, `4H`)을 실제 캔들 갯수로 변환.
   - 메인 DB(`daily_ohlcv` 또는 `minute_ohlcv`)에서 서브쿼리 `ORDER BY volume DESC LIMIT 1`로 지정 기간 내 최대 거래량 캔들을 찾음.
   - 현재가가 그 캔들의 `high`를 돌파했는지 판별. 돌파한 종목과 돌파율(%)을 추출.
5. **테스트 및 검증 (단위 테스트)**
   - 악성 파라미터가 들어왔을 때 ValueError가 발생하는지, SQL 주입이 완벽히 방어되는지 확인.

## 3. 리스크 및 완화 전략
- **리스크**: `disparity_value` 쿼리 작성 시, `connect_sqlite()` 메인 커넥션에서 `connect_ma_db()` 테이블을 동시에 쿼리해야 하므로 `ATTACH DATABASE` 구문이 필수적임.
- **완화 전략**: 쿼리 상단에 `ATTACH DATABASE 'file:madb?mode=memory&cache=shared' AS madb;` 구문을 실행하여 동일 트랜잭션 내에서 조인이 가능하도록 구현.
