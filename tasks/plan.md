# Implementation Plan: 종목 마스터 심화 필터링 및 단일 스케줄러 구축

## Overview
Trading Server의 종목 필터링 로직을 고도화하여 단기과열, 저유동성, 투자주의 환기종목 등 자동매매에 위험한 종목을 사전에 제거합니다. 또한 1 OCPU/1GB RAM 환경의 서버 안정성을 위해 파편화된 스케줄러를 `SystemScheduler` 하나로 통합하여 중앙 집중식으로 배치 작업을 관리합니다.

## Architecture Decisions
- **단일 스케줄러 (SystemScheduler)**: 서버 리소스 한계를 극복하고 OOM을 방지하기 위해 단 하나의 `AsyncIOScheduler` 인스턴스만 유지합니다. 6분의 1분봉 수집 레이턴시는 시스템 단순성을 위해 기꺼이 감수합니다.
- **매일 08:30 마스터 DB 덮어쓰기**: 당일 아침에 거래정지나 단기과열로 지정된 종목을 타겟 리스트에서 완벽하게 증발시키기 위해 매일 아침 DB를 `replace` 모드로 갱신합니다.
- **스키마 최적화**: 실시간 조인이 가능하거나 전략적 의미가 없는 `prev_vol`과 `capital`을 저장 시 제거하여 I/O를 최적화합니다.

## Task List

### Phase 1: Foundation (마스터 데이터 필터링)
- [ ] Task 1: 종목 마스터 심화 필터링 및 컬럼 다이어트 구현

### Checkpoint: Foundation
- [ ] `stock_codes` 테이블 생성 로직이 문제없이 동작하고 필터링이 올바르게 적용된다.
- [ ] `trading.db` 내 `stock_codes` 데이터의 컬럼이 축소되었음을 확인한다.

### Phase 2: Centralized Scheduling
- [ ] Task 2: 중앙 집중형 스케줄러(`SystemScheduler`) 생성
- [ ] Task 3: 메인 앱과 신규 스케줄러 연동 및 구형 스케줄러 폐기

### Checkpoint: Complete
- [ ] 서버 기동 시 에러 없이 `SystemScheduler`가 켜진다.
- [ ] 부팅 직후 `Auth` 잡이 즉시 실행되고, 스케줄 리스트에 08:30(종목 초기화)과 22:00(인증) 잡이 정상적으로 등록된다.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| 마스터 데이터 다운로드 URL 변경/장애 | High | KIS 공식 URL이므로 안정적이나, 다운로드 실패 시 `try-except`로 이전 마스터 데이터를 유지하도록 예외 처리. (기본 내장됨) |
| 단일 스케줄러 CPU 스파이크 | Med | 08:30 (초기화)와 22:00 (인증) 등 묵직한 작업의 스케줄링 시간대를 완전히 분산시켜 충돌을 방지. |

## Open Questions
- None. (모든 논의 완료)
