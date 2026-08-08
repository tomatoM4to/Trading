# Plan: In-Memory 휘발성 이평선(MA) 전용 아키텍처 도입

## 1. 개요 (Overview)
디스크 I/O 없이 순수 파이썬(Pure Python)과 In-Memory DB를 조합하여 MA 데이터를 관리/조회하는 아키텍처로의 전환을 위한 구현 계획입니다.

## 2. 주요 컴포넌트 및 의존성 (Components & Dependencies)
- **`core/database.py`**: 기존 디스크 연결과 완전히 독립적인 `file::memory:?cache=shared` 전용 MA 커넥션 풀을 관리합니다.
- **`core/ma_calculator.py` (신규)**: Pandas 없이 `collections.deque`를 활용해 2,400개 종목의 종가(Close)를 캐싱하고 O(1) 수준으로 MA를 연산하는 엔진입니다.
- **`core/bootstrap.py`**: 매일 08:00 또는 서버 기동 시 인메모리 DB를 비우고, 디스크 DB에서 최소한의 OHLCV(일봉 300일, 분봉 2일)를 꺼내와 MA를 리빌드하는 파이프라인.
- **`core/scheduler.py`**: 실시간 장중 캔들 수집 시 OHLCV는 디스크에 넣고, MA는 계산기를 통해 인메모리에 넣도록 역할을 이원화합니다.
- **`services/screener_service.py`**: 무거운 `AVG() OVER()` 윈도우 함수 쿼리를 제거하고 `SELECT * FROM minute_ma` 단순 조회로 전면 개편합니다.

## 3. 구현 순서 (Implementation Order)
1. **DB 및 스키마 세팅**: 인메모리 커넥션 분리 및 `daily_ma`, `minute_ma` 스키마 작성.
2. **MA Calculator 엔진**: 순수 파이썬 캐시 엔진 구현 및 정확도 테스트.
3. **Bootstrapping (리빌드)**: 디스크 -> 캐시 -> 메모리 DB 로딩 파이프라인 구현.
4. **Real-time Scheduler**: 장중 분봉/일봉 스케줄러에 캐시 연산 및 메모리 DB Insert 연동.
5. **Screener Refactoring**: 스크리너 엔진의 SQLite Push-down 쿼리 롤백 및 제한(Validation) 로직 추가.

## 4. 리스크 및 완화 전략 (Risks & Mitigations)
- **리스크**: 콜드스타트 리빌드 시 디스크에서 수십만 건의 OHLCV를 `fetchall()`로 한 번에 가져오면 일시적인 메모리 스파이크가 발생할 수 있습니다.
- **완화**: SQLite의 커서를 이용해 Chunk 단위(`fetchmany()`)로 읽어 파이썬 `MACalculator`에 스트리밍하듯 집어넣어 메모리 사용량을 평탄화(Flat)합니다.

## 5. 검증 체크포인트 (Verification)
- [ ] `MACalculator`의 결과값이 기존 시스템(또는 수작업 엑셀)의 MA5~MA200 값과 100% 일치하는지.
- [ ] 08:00 부트스트랩 리빌드 완료 후 전체 파이썬 프로세스 메모리 사용량이 예상치(350MB 이내)를 준수하는지.
- [ ] 장중 스케줄러가 디스크 Lock 에러나 타임아웃 없이 두 DB에 분리 삽입을 성공하는지.
- [ ] 스크리너 엔진 호출 시 속도가 밀리초(ms) 단위로 O(1) 수준으로 떨어졌는지.
