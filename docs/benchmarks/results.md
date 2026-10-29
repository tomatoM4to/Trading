# 벤치마크 결과와 측정 자산

[벤치마크 진입점](../benchmark.md) · [하네스](harness.md) · [이력](history.md)

## 최신 보존 결과: 개선 12개 시나리오

기록상 2026-08-22 12:18 KST, Oracle Cloud 1 OCPU / 1GB RAM 서버 측정이다. 시각·환경은 당시 dev 문서의 설명이며 CSV 자체에는 호스트, 자원, 타임존, 코드 SHA, DB 스냅샷이 없다. 파일명의 시각은 실행 시작 시 생성되는 클라이언트 로컬 시각이다.

출처: [원본 CSV](https://github.com/tomatoM4to/Trading/blob/b8e94dd88064fee47895362b736d49c0cd4b4cf2/docs/benchmark-result/screener_benchmark_20260822_121829.csv) · [당시 설명](https://github.com/tomatoM4to/Trading/blob/b8e94dd88064fee47895362b736d49c0cd4b4cf2/docs/benchmark.md). 원본은 dev에 있고 이 문서에는 값을 전사했다.

| 시나리오 | 시간(s) | 종목 수 | CSV 상태 |
|---|---:|---:|---|
| Light 1 (Daily Alignment, 5 Sessions) | 5.407 | 323 | Success |
| Light 2 (Daily Golden Cross, 20 Sessions) | 6.024 | 2041 | Success |
| Light 3 (Minute Golden Cross, 60 Minutes) | 9.694 | 2301 | Success |
| Light 4 (Daily Convergence, 10 Sessions) | 5.358 | 69 | Success |
| Light 5 (Daily MA20 Disparity Above 105) | 6.711 | 480 | Success |
| Light 6 (Daily 1M Volume Peak Breakout) | 9.774 | 629 | Success |
| Light 7 (Three-Way Daily Opportunity OR) | 21.52 | 2158 | Success |
| Heavy 1 (Daily 300-Candle Alignment Scan) | 8.971 | 0 | Success |
| Heavy 2 (Minute 390-Candle Alignment Scan) | 12.815 | 0 | Success |
| Heavy 3 (Minute 390-Candle Convergence Scan) | 14.531 | 1607 | Success |
| Heavy 4 (Three-Way Full-Scan OR) | 43.074 | 2285 | Success |
| Heavy 5 (Two-Way Multi-Timeframe OR) | 29.269 | 2256 | Success |

단독 Light는 5.358~9.774초, Light OR는 21.520초다. 단독 Heavy는 8.971~14.531초, 2분기 OR는 29.269초, 3분기 OR는 43.074초다. 각 행은 단일 관측값으로 읽으며 반복 평균이나 p95가 아니다.

Heavy 1·2의 0건은 CSV상 성공 종료와 함께 기록됐다. 당시 문서는 긴 정배열 유지 조건으로 설명하지만, CSV만으로 기대 정답 집합을 검증할 수는 없다. 0건을 자동으로 오류 또는 정답으로 판정하지 않는다.

## 같은 날의 기존 10개 시나리오

기록상 2026-08-22 12:00 KST 서버 측정이다. 아래와 위는 서로 다른 시나리오 세트다. 개선 전후 성능비가 아니라 **기존 구성의 마지막 보존 관측과 새 구성의 첫 보존 관측**으로 구분한다.

출처: [원본 CSV](https://github.com/tomatoM4to/Trading/blob/b8e94dd88064fee47895362b736d49c0cd4b4cf2/docs/benchmark-result/screener_benchmark_20260822_120010.csv).

| 시나리오 | 시간(s) | 종목 수 | CSV 상태 |
|---|---:|---:|---|
| Light 1 (Daily Cross) | 5.359 | 8 | Success |
| Light 2 (Minute Cross) | 9.654 | 166 | Success |
| Light 3 (Daily Alignment) | 5.463 | 476 | Success |
| Light 4 (Minute Convergence Point) | 12.339 | 2324 | Success |
| Light 5 (Daily Alignment + Foreign Buy Rank) | 0.278 | 25 | Success |
| Heavy 1 (Daily Deep Window) | 0.528 | 0 | Success |
| Heavy 2 (Minute Stress Test) | 0.613 | 0 | Success |
| Heavy 3 (Mixed Timeframes Combo) | 0.302 | 0 | Success |
| Heavy 4 (Extreme Window Functions) | 0.27 | 0 | Success |
| Heavy 5 (Full Minute DB Scan) | 0.512 | 0 | Success |

## 전체 원시 자산 목록

main의 CSV 14개는 모두 그대로 보존한다. dev는 이 중 로컬 결과 6개를 제거하고 서버 결과 2개를 추가했지만, 문서 통합에서는 로컬 기록도 독립 실험 이력으로 유지한다. 환경과 단계 분류는 당시 문서에 근거하며 CSV만으로 입증되는 값은 아니다.

| 파일 시각 | 기록상 환경·단계 | 구성 | CSV Success / 전체 | 위치 |
|---|---|---|---:|---|
| 20260804_145625 | 서버 · 초기 오류 포함 | 기존 10개 | 5 / 10 | [CSV](../benchmark-result/screener_benchmark_20260804_145625.csv) |
| 20260804_150706 | 서버 · 초기 오류 포함 | 기존 10개 | 5 / 10 | [CSV](../benchmark-result/screener_benchmark_20260804_150706.csv) |
| 20260804_152738 | 서버 · 쿼리 수정 후 | 기존 10개 | 4 / 10 | [CSV](../benchmark-result/screener_benchmark_20260804_152738.csv) |
| 20260804_215830 | 로컬 · 인메모리 기준 | 기존 10개 | 10 / 10 | [CSV](../benchmark-result/screener_benchmark_20260804_215830.csv) |
| 20260804_222615 | 서버 · 인메모리 | 기존 10개 | 6 / 10 | [CSV](../benchmark-result/screener_benchmark_20260804_222615.csv) |
| 20260804_224407 | 서버 · 인메모리 재측정 | 기존 10개 | 6 / 10 | [CSV](../benchmark-result/screener_benchmark_20260804_224407.csv) |
| 20260805_212946 | 로컬 · AST 비용 정렬 | 기존 10개 | 10 / 10 | [CSV](../benchmark-result/screener_benchmark_20260805_212946.csv) |
| 20260805_215007 | 로컬 · 후보 push-down | 기존 10개 | 10 / 10 | [CSV](../benchmark-result/screener_benchmark_20260805_215007.csv) |
| 20260805_215923 | 로컬 · 단방향 윈도우 | 기존 10개 | 10 / 10 | [CSV](../benchmark-result/screener_benchmark_20260805_215923.csv) |
| 20260806_185510 | 서버 · 최적화 적용 | 기존 10개 | 10 / 10 | [CSV](../benchmark-result/screener_benchmark_20260806_185510.csv) |
| 20260808_213722 | 서버 · MA 전용 엔진 전 | 기존 10개 | 10 / 10 | [CSV](../benchmark-result/screener_benchmark_20260808_213722.csv) |
| 20260808_215546 | 로컬 · MA 전용 엔진 전 | 기존 10개 | 10 / 10 | [CSV](../benchmark-result/screener_benchmark_20260808_215546.csv) |
| 20260808_222427 | 로컬 · MA 전용 엔진 후 | 기존 10개 | 10 / 10 | [CSV](../benchmark-result/screener_benchmark_20260808_222427.csv) |
| 20260809_000809 | 서버 · MA 전용 엔진 후 | 기존 10개 | 10 / 10 | [CSV](../benchmark-result/screener_benchmark_20260809_000809.csv) |
| 20260822_120010 | 서버 · 디스크 OHLCV + 메모리 MA | 기존 10개 | 10 / 10 | [CSV](https://github.com/tomatoM4to/Trading/blob/b8e94dd88064fee47895362b736d49c0cd4b4cf2/docs/benchmark-result/screener_benchmark_20260822_120010.csv) |
| 20260822_121829 | 서버 · 독립 Heavy 기준선 | 개선 12개 | 12 / 12 | [CSV](https://github.com/tomatoM4to/Trading/blob/b8e94dd88064fee47895362b736d49c0cd4b4cf2/docs/benchmark-result/screener_benchmark_20260822_121829.csv) |

`Success` 합계는 저장된 문자열을 센 것이지 독립 검증 결과가 아니다. 과거 실행기 버전 전체를 복원하지 않았으며, 확인한 main 실행기에는 SSE 오류를 놓칠 수 있는 경계가 있다. [하네스의 완료 판정](harness.md)을 함께 읽는다.

## 출처와 보존 경계

- main의 CSV 14개: `652bb24da07e35c07539997d9faa10413a414eba` 트리 기준.
- dev의 12:00 CSV 추가: `e45b1770c72bb736e99b6ea89db06d193fdf92ac` 커밋.
- dev의 12:18 CSV·개선 실행기·계약 테스트 추가: `2db743b217981989506f578f7895770315590acd` 커밋.
- 위 커밋은 파일이 보존된 출처다. 실제 측정 시 서버에 배포됐던 정확한 커밋이라고 단정하지 않는다.
- 이번 정리에서는 원시 CSV의 삭제·병합·재작성이나 신규 성능 측정을 하지 않았다.
