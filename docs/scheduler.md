# 스케줄러와 수집 파이프라인

## SystemScheduler

`SystemScheduler`는 프로세스 내 단일 `AsyncIOScheduler`를 감싼 싱글턴이다. 각 작업은 `max_instances=1`, `coalesce=True`로 등록된다. 시간대는 서버와 컨테이너의 `Asia/Seoul` 설정을 전제로 한다.

| 시각 | 작업 | 주요 효과 |
|---|---|---|
| 04:00 | `cleanup_ohlcv_job` | 거래일 기준 보존 개수로 일봉·분봉 GC 후 디스크 동기화 |
| 08:30 | `refresh_stock_codes_job` | 종목 마스터와 상태·재무 정보 갱신 후 동기화 |
| 08:55 | `start_minute_ohlcv_job` | 장중 분봉 수집 루프 시작 |
| 16:00 | `run_daily_ohlcv_job` | 전 종목 일봉 갭필·갱신 후 동기화 |
| 22:00 | `refresh_auth_job` | 다음 거래일을 위한 KIS 토큰 강제 갱신 |

## 부트스트랩

`run_bootstrap_pipeline()`은 앱 시작 시 `SCHED=True`일 때 백그라운드로 실행된다. 현재 데이터 상태를 검사하고 필요한 마스터·일봉·분봉 준비 작업과 MA 재구축을 순차 실행한다.

`rebuild_ma_database()`는 다음을 수행한다.

1. 시스템 상태를 acquire해 `/health` 외 API를 차단한다.
2. MA 계산기와 두 MA 테이블을 초기화한다.
3. `daily_ohlcv`를 시간 오름차순으로 순회해 일봉 MA를 재생성한다.
4. 최근 3개 거래일의 `minute_ohlcv`로 분봉 MA를 재생성한다.
5. 연결을 닫고 시스템 상태를 복구한다.

`SCHED=False`에서도 스크리너 사용을 위해 MA 재구축 태스크는 시작된다.

## 일봉 수집

`app/tasks/daily_ohlcv_scheduler.py`는 종목별 기존 최신 날짜를 확인하고 KIS 일봉 API로 부족한 구간을 가져온다. 결과는 STRICT 스키마에 맞게 정수로 변환하고 bulk upsert한다.

- 전 종목을 하나의 DataFrame으로 만들지 않는다.
- KIS 호출은 전역 큐를 사용한다.
- 종목 단위 실패가 전체 프로세스를 즉시 중단하지 않도록 기록한다.
- 완료 뒤 호출자가 메모리 DB를 디스크에 동기화한다.

## 분봉 수집

`app/tasks/minute_ohlcv_scheduler.py`는 08:55부터 장중 수집을 수행한다. 종목별 분봉 응답의 누적 거래량·대금을 단위 캔들 값으로 변환해 저장하며, 같은 캔들의 갱신은 upsert한다.

새 종가는 `MACalculator`에 전달되고 `minute_ma`에 해당 시점의 MA가 저장된다. KIS 요청 순서는 전역 큐가 직렬화한다.

## 지능형 GC

GC는 전일 데이터가 존재하는지 먼저 확인하는 smart trigger를 사용한다. 실행할 필요가 있을 때 임시 테이블과 윈도 순위를 이용해 종목별 최신 거래 캔들만 보존한다.

- 일봉: 종목별 최신 500개
- 분봉: 종목별 최신 2개 거래일
- 전 종목 Python 삭제 루프 대신 집합 기반 SQL 사용
- 실행 중 `system_state.acquire()`로 일반 API 차단
- 완료 후 메모리 DB를 디스크에 동기화

## 변경 시 확인사항

- 예약 시각이 장 운영 시간과 충돌하지 않는가
- 동일 작업의 중복 실행이 차단되는가
- 모든 KIS 호출이 큐를 통과하는가
- 독립 SQLite 연결이 `finally`에서 닫히는가
- 무거운 작업이 시스템 가드를 acquire하는가
- 성공 뒤 필요한 디스크 동기화가 실행되는가
- 1GB 환경에서 전 종목 데이터 복제본을 만들지 않는가
