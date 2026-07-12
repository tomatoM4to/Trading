# [Idea] Pandas 폐기 및 순수 SQLite 윈도우 함수(엔진 푸시다운) 도입

## Problem Statement
우리는 어떻게 하면 1 OCPU/1GB RAM 서버 환경에서, 별도의 외부 라이브러리나 프론트엔드 위임 없이 동시 접속자의 '동적 파라미터 기반 2,400종목 돌파 스크리닝'을 1초 이내에 처리할 수 있을까?

## Recommended Direction
**"Pandas 기반 온디맨드 연산 폐기 및 순수 SQLite 윈도우 함수 기반의 연산 푸시다운(Pushdown)"**
데이터 수집(Write)은 기존처럼 Pandas를 활용해 SQLite에 저장한다. 그러나 API 조회(Read & Compute) 시점에는 `pd.DataFrame`을 일절 생성하지 않는다. 대신 파이썬은 사용자의 동적 파라미터(`target_mas` 등)를 순수 SQL의 `WITH` 절(CTE)과 `AVG() OVER()` 윈도우 함수 쿼리로 변환하여 SQLite에 직접 던진다. 파이썬의 GIL과 메모리 복사 병목을 우회하고, SQLite의 C 엔진이 연산을 끝낸 최종 핫리스트 결과만 파이썬으로 반환받는다.

## Key Assumptions to Validate
- [ ] SQLite의 윈도우 함수가 60만 건(2,400종목 * 250일)의 복합 이동평균 쿼리를 1 OCPU 환경에서 1초 이내에 리턴하는가?
- [ ] 파이썬 코드의 `rolling().mean().shift(1)` 로직을 SQL의 `ROWS BETWEEN N PRECEDING AND 1 PRECEDING` 로 오차 없이 번역할 수 있는가?

## MVP Scope
1. 기존 `calculate_breakout` 파이썬 함수를 무효화.
2. SQLAlchemy(또는 raw sqlite3)를 사용하여 사용자의 동적 변수를 주입받아 SQLite CTE 쿼리 문자열을 생성하는 `build_screener_query` 함수 작성.
3. 생성된 쿼리를 `trading.db`에 던져 속도를 측정하는 프로파일링 스크립트 작성.

## Not Doing (and Why)
- **프론트엔드 연산 위임**: 네트워크 병목과 모바일 크래시를 유발하므로 철회.
- **DuckDB 도입**: 60만 건의 데이터는 순수 SQLite만으로도 1초 컷이 가능하므로, 오버엔지니어링 방지를 위해 도입하지 않음.
- **조회 시점의 Pandas 사용**: 30초 병목의 주범이므로 API 로직에서 완전 퇴출.
