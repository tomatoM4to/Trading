# Idea: Advanced Screener Filters (Disparity, Convergence, Institutions, Volume Profile)

## Problem Statement
"어떻게 하면 1GB RAM 서버의 메모리와 CPU를 고갈시키지 않으면서, 이격도, 매물대, 기관/외국인 수급 같은 고급 필터들을 스크리너 파이프라인에 추가할 수 있을까?"

## Recommended Direction
난이도와 연산 특성에 따라 아키텍처를 철저히 분리(Decoupling)하여 서버 부하를 0으로 만듭니다.

1. **이격도 (Disparity) & 수렴 (Convergence)**:
   - 기존 '이평선 정배열'과 동일하게 **SQLite 내부 동적 쿼리(Window Function)**로 밀어 넣습니다(Push-down).
2. **외국인/기관 순매수 (Institutions/Foreigners)**:
   - KIS API의 '당일 순매수 상위 랭킹 API'를 호출하여 티커 Set을 만든 뒤, 기존 기술적 필터 결과와 `&` (교집합) 처리합니다.
3. **매물대 (Volume Profile)**:
   - 실시간 동적 연산을 포기하고 **사전 연산(Pre-calculation)** 전략을 취합니다.
   - 1GB RAM 서버에서 2,400개 종목의 매물대를 장중에 실시간으로 그리는 것은 불가능에 가깝습니다. 따라서 매일 장 마감 후 빈 시간대(야간/새벽)에 스케줄러가 일봉(또는 분봉) 데이터를 바탕으로 "가장 두꺼운 매물대(POC) 가격대"를 계산하여 별도 테이블(`daily_volume_profile`)에 저장합니다.
   - 스크리너에서는 단순히 `WHERE current_price > poc_top` (매물대 돌파) 등으로 1회성 조회만 수행합니다.

## Key Assumptions to Validate
- [ ] KIS API의 순매수 상위 랭킹 데이터만으로도 유저가 원하는 "수급 빵빵한 종목"을 충분히 걸러낼 수 있는가?
- [ ] 매물대를 "야간에 사전 계산된 전일 기준 가장 두꺼운 매물대 1~2개"로 정의해도 현재 차트 매매(Breakout 전략) 관점에서 유효한가? (답변: 현실적인 인프라 타협점으로서 유효함)

## MVP Scope
- **Phase 1 (쉬운 것들)**: 이격도(Disparity), 수렴(Convergence), 외국인/기관 수급(Foreign/Inst) 필터 적용.
- **Phase 2 (매물대)**: 야간 백그라운드 스케줄러에 매물대(Volume Profile) 계산 워커 추가 및 DB 스키마 설계, 스크리너 쿼리 연동.

## Not Doing (and Why)
- **장중 실시간 분봉 틱 단위 매물대 계산**: 서버 스펙(1 OCPU / 1GB RAM) 상 감당할 수 없으며, 전략의 핵심이 '단타'가 아니라 '추세 돌파'라면 어제까지 누적된 거대한 일봉 매물대를 오늘 돌파하느냐가 더 중요하므로 과감히 제외합니다.
