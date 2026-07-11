# Implementation Plan: Master Stock List Refactoring

## Overview
기존 마스터 종목 리스트(`stock_codes`) 초기화 로직은 '관리종목', '단기과열' 등의 위험 종목을 DB 삽입 전 단계에서 삭제(Drop)해버렸습니다. 이를 수정하여 ETF/스팩 등 비주식 종목만 삭제하고, 모든 주식(ST) 종목을 데이터베이스에 저장합니다. 동시에 KIS 마스터 파일에 존재하는 재무제표(ROE, 영업이익 등) 및 위험 지표(상태 플래그)들을 `stock_codes` 테이블의 새로운 컬럼으로 확장하여, 향후 On-Demand Screener가 로컬 DB에서 유연하게 조건 검색을 할 수 있는 기반을 마련합니다.

## Architecture Decisions
- **DB 스키마 유지 정책:** 위험 종목이라도 삭제하지 않고 원본을 보존하되, Boolean(또는 Y/N) 플래그를 두어 쿼리 레벨에서 동적으로 제어(Filtering)할 수 있게 합니다.
- **컬럼 통합 매핑:** 코스피와 코스닥 마스터 파일의 한글 컬럼명이 서로 다르므로(예: `단기과열` vs `단기과열종목구분코드`), 파이썬의 `rename` 딕셔너리를 사용해 통일된 영문 스키마로 병합(Concat)합니다.
- **재무 데이터 형변환:** 매출액, 영업이익, 당기순이익, ROE 등은 문자열(String)로 들어오므로, `pd.to_numeric`을 사용하여 숫자형(Float/Int) 데이터로 변환 후 DB에 적재합니다.

## Task List

### Phase 1: Foundation (문서화 및 스키마 정의)
- [ ] Task 1: `docs/database.md` 스키마 문서 업데이트
  - 기존 `stock_codes` 테이블 명세에 재무 지표(revenue, operating_profit, net_income, roe) 및 상태 플래그(is_halted, is_admin_issue, is_overheated 등) 컬럼을 추가합니다.

### Phase 2: Core Features (리팩토링 구현)
- [ ] Task 2: `app/tasks/init_stock_codes.py` 파싱 및 필터링 로직 수정
  - 비주식(그룹코드 != 'ST' 및 SPAC 등)만 필터링하고, 상태 불량 종목(거래정지, 관리종목 등)은 필터링하지 않고 유지합니다.
  - 코스피/코스닥 각각의 `rename` 딕셔너리에 신규 컬럼(재무 및 위험 지표)을 추가 매핑합니다.
  - 숫자형 데이터 리스트에 신규 재무 지표를 추가하여 형변환 로직을 태웁니다.

### Checkpoint: Complete
- [ ] 스크립트 실행 시 오류 없이 `trading.db`의 `stock_codes` 테이블이 생성되는가?
- [ ] 테이블 조회 시 총 2,400여 개 종목이 존재하며, 관리종목이나 재무 데이터가 누락 없이 들어가 있는가?

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| 형변환 오류 (빈 문자열 등) | High | `pd.to_numeric(errors="coerce").fillna(0)` 처리로 안전하게 변환 |
| KOSPI/KOSDAQ 컬럼명 불일치 | Med | 파싱 스크립트(`kis_kospi_code_mst.py` 등)의 리턴 컬럼명을 다시 한번 더블 체크 후 매핑 적용 |

## Open Questions
- 상태 플래그 데이터를 DB에 넣을 때 'Y'/'N' 텍스트 그대로 넣을지, 아니면 1/0 (Boolean/Integer) 형태로 형변환해서 넣을지 결정이 필요합니다. (본 계획은 쿼리 최적화를 위해 가능하면 Integer 1/0 형변환을 권장합니다.)
