# ADR-035: 스크리너 이격도 및 매물대 돌파 알고리즘의 초경량 구현 (Push-down & Approximation)

## Status
Accepted

## Date
2026-08-13

## Context
실전 트레이딩에서 가장 승률이 높은 타점 중 두 가지는 "이평선 대비 과대낙폭(또는 강한 모멘텀)"을 뜻하는 **이격도(Disparity)**와, "과거 가장 많은 돈이 몰렸던 강력한 저항선"을 뚫는 **매물대 돌파(Volume Profile Breakout)**입니다.
하지만 사용자는 당초 "매 캔들(OHLCV)을 수집할 때마다 이격도와 매물대를 실시간 계산하여 디스크에 저장"하는 방식을 제안했습니다.
이는 1 OCPU / 1GB RAM이라는 가혹한 서버 제약(디스크 I/O 병목 및 메모리 한계)을 회피하기 위해 기존에 정립한 **Zero-Latency In-Memory MA 아키텍처(ADR-026)**에 정면으로 위배되며, 서버 OOM과 파일 잠금(Lock) 에러를 유발할 위험이 큽니다.

## Decision
추가적인 백그라운드 연산이나 디스크 저장을 완벽히 배제하고, 기존 In-Memory 구조의 이점을 극대화하는 **초경량 근사치(Approximation) 및 DB Push-down 기법**을 채택합니다.

### 1. 이격도 (`disparity_value`) - ATTACH DATABASE 조인
- 새로 계산해 저장할 필요 없이, 이미 메모리 상에 존재하는 `daily_ohlcv`의 종가(close)와 전용 MA DB(`ma_db?mode=memory`)의 이평선 값을 실시간으로 엮어서 계산합니다.
- 스크리너 필터 실행 시 쿼리 상단에 `ATTACH DATABASE 'file:ma_db?mode=memory&cache=shared' AS madb;` 구문을 실행하여 메인 DB와 MA DB를 동일 트랜잭션 내에서 조인합니다.
- `(close / ma_line) * 100` 수식을 DB 단에서 직접 연산하여 필터링(`<=` 또는 `>=`)합니다.

### 2. 매물대 돌파 (`volume_peak_breakout`) - 단일 캔들 근사(Approximation) 기법
- 수많은 캔들의 가격을 10등분하여 누적 거래량을 정밀하게 그리는 전통적인 방식은 연산 부하가 심합니다.
- 트레이딩 관점(프라이스 액션)에서 가장 핵심이 되는 매물대는 결국 **"가장 많은 거래량이 터진 캔들(Point of Control, Max Volume Candle)"**이라는 점에 착안합니다.
- `ORDER BY volume DESC LIMIT 1`과 같은 서브쿼리(혹은 Window Function)를 통해 지정 기간(예: 30일, 60일) 내의 최고 거래량 캔들을 찾아내고, 현재가가 해당 캔들의 고가(High)를 돌파했는지만을 판별합니다.
- 쿼리 코스트를 통제하고 클라이언트의 임의 주입을 막기 위해 탐색 기간(Lookback)을 `1M`, `3M`, `2H`, `4H`의 4가지 고정 프리셋으로만 제한합니다. (Smart Defaults)

## Consequences
- **제로 풋프린트**: 디스크 I/O 추가가 전혀 없으며, 백그라운드 워커의 부하가 0%입니다.
- **성능 확보**: 무거운 로직을 애플리케이션 메모리(DataFrame)로 가져오지 않고 SQLite 인메모리 상에서 `JOIN`과 `Window Function`으로 처리(Push-down)하여 60초 타임아웃 이내에 빠른 응답이 보장됩니다.
- **유지보수성**: 이격도 산출과 매물대 탐색 로직이 쿼리 안에 캡슐화되어 유지보수가 용이해졌습니다.
