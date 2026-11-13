# 스크리너 벤치마크

## 현재 측정기

`scripts/benchmark_screener.py`는 격리된 디스크 SQLite와 고유 MA 메모리 DB에서 고정 합성 데이터를 생성한다. 원격 서버와 KIS API를 호출하지 않는다. 이전 HTTP 측정기의 error/미완료 SSE를 Success로 기록할 수 있는 판정과 독립 기대값 부재를 제거했다. 기존 `--host` 옵션은 폐기했다.

```powershell
uv run --locked python scripts/benchmark_screener.py --tickers 64 --repeats 3
```

일봉 500개·분봉 590개를 종목별로 적재하고 실제 부트스트랩 MA 재구축을 실행한다. 종목의 절반은 상승, 절반은 하락 시계열이다. 실제 스크리너 SSE가 단 하나의 complete로 끝나고, 모든 기대 종목과 필터 값이 독립 산술 기준에 일치해야 시간과 성공을 기록한다. 오류·미완료·잘못된 빈 결과는 측정 실패다. 정확성 하네스와 별도 명령으로 유지하며, 전 종목 시계열을 하나의 DataFrame으로 복제하지 않는다.

`--tickers` 범위는 2..2400, `--repeats`는 1..20이다. 기본 64종목 측정을 운영 전체 규모의 성능으로 일반화하면 안 된다. 로그에는 처리 레코드, MA 보존 행, 준비 시간, 반복별 시간/성공·실패·검색 수, Python 프로세스 peak RSS가 포함된다. 준비 시간은 Fixture 생성·저장·MA 재구축 전체이고, RSS는 OS page cache를 제외한 프로세스 최고치다.

2026-11-13 Windows / Python 3.12.12 / SQLite 3.50.4 단일 실행: 64종목, 69,760 OHLCV행, daily_ma 19,264행, minute_ma 25,024행. 준비 1.543초, 3회 조회 0.0251..0.0262초, 매회 32종목과 전체 필터 값 일치, peak RSS 약 93.9MiB. CPU/메모리 제한이 없는 로컬 단기 측정이며 Linux 1 OCPU/1GB 결과가 아니다. 결과 JSON은 사용자 요청으로 제거하고 측정 조건과 요약만 보존했다.

이번 환경에서는 Docker 엔진 접근이 거부돼 제한 컨테이너를 실행하지 못했다. 장시간 RSS·2400종목·heavy query 중 응답성은 [미검증 범위](testing.md#실행-결과와-한계)에 기록했다. HTTP·외부 수급을 포함한 과거 CSV와 현재 합성 로컬 결과는 동일 입력/환경이 아니므로 속도 회귀 비교에 직접 사용하지 않는다.

## 과거 기록 보존

아래 내용과 CSV는 과거 구조·데이터·서버에서 얻은 실험 기록이다. 당시의 성공 판정/결함이 포함될 수 있으며 현재 품질이나 성능의 보증이 아니다. 현재 구조는 [database.md](database.md), 새 검증 근거는 [testing.md](testing.md)를 따른다.


## 5. 벤치마크 결과 히스토리
서버(Oracle Cloud 1GB RAM)와 로컬 환경에서 점진적인 아키텍처 최적화를 수행하며 측정한 결과들입니다.

### ☁️ 운영 서버 (Oracle Cloud, 1GB RAM)
1. 초기 최적화 전 (버그 포함)
- 참고: 1, 2차 테스트는 `Short-circuit` 버그로 인해 쿼리가 무시되어 0초로 기록된 결과입니다.
- [screener_benchmark_20260804_145625.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260804_145625.csv)
- [screener_benchmark_20260804_150706.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260804_150706.csv)

2. 버그 해결 후 정밀 테스트
- 참고: 정상적으로 DB 쿼리가 수행되었으나, 디스크 I/O 병목으로 인해 쿼리 소요 시간이 수십 초에 달했습니다.
- [screener_benchmark_20260804_152738.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260804_152738.csv)

3. In-Memory DB 최적화 도입
- 최적화 성과: Disk I/O를 0으로 만들어 전반적인 속도는 올랐으나, 분봉 데이터 윈도우 함수 처리 시 1GB RAM 환경의 연산 한계로 인해 60초 타임아웃(Timeout)이 다수 발생했습니다.
- [screener_benchmark_20260804_222615.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260804_222615.csv)
- [screener_benchmark_20260804_224407.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260804_224407.csv)

4. 1차~4차 아키텍처 최적화 전면 적용 (서버 최종본)
- 최적화 성과: 로컬에서 검증된 최적화 기법(AST Cost 정렬, 동적 Ticker 푸시다운, 단방향 윈도우 등)을 1GB RAM 운영 서버에 모두 적용 후 측정한 최종 결과입니다. 풀스캔이 발생하는 단순 시나리오(Light 1~4)는 11~23초 소요되나, 수급 필터나 복합 조건이 포함된 시나리오들(Light 5, Heavy 1~5)은 사전 파티션 축소(지연 평가) 및 Short-circuit 덕분에 **전부 0.6초 이내(기존 60초 타임아웃 대비 99% 이상 단축)**에 처리되는 극적인 성능 최적화를 달성했습니다.
- [screener_benchmark_20260806_185510.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260806_185510.csv)

5. 인메모리 MA 엔진 도입 전 (서버 베이스라인 재측정)
- 참고: 현재 파이썬 MA 엔진 도입 직전에 측정한 과거 서버 성능입니다. 분봉 윈도우 풀스캔 연산(Light 2, Light 4) 시 약 28~30초가 소요됐습니다.
- [screener_benchmark_20260808_213722.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260808_213722.csv)

6. 인메모리 MA 도입 후
- 30%~50% 개선
- [screener_benchmark_20260809_000809.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260809_000809.csv)

### 💻 로컬 머신 (High Spec)
> 참고: 로컬 환경은 리소스가 넉넉하여 무거운 쿼리도 타임아웃이 발생하지 않았으며, 순수한 알고리즘 및 쿼리 최적화의 효과를 정밀하게 추적하기 위해 사용되었습니다.

1. In-Memory DB 기준 측정 (로컬 베이스라인)
- 참고: 디스크 병목은 없으나, 무거운 분봉 스트레스 쿼리(Heavy 2)의 경우 로컬에서도 **약 16.5초** 이상 소요되었습니다.
- [screener_benchmark_20260804_215830.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260804_215830.csv)

2. AST 파이프라인 최적화 (휴리스틱 Cost 정렬)
- 최적화 성과: 가벼운 API 기반 필터를 우선 실행(Cost 0)하도록 재정렬하여 초기 종목 파티션을 크게 축소했습니다.
- [screener_benchmark_20260805_212946.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260805_212946.csv)

3. 동적 Ticker 푸시다운 (Push-down)
- 최적화 성과: 앞서 축소된 종목 리스트 30개를 SQL 쿼리에 직접 주입(`WHERE ticker IN (...)`)하여 풀스캔을 차단했습니다. 그 결과 로컬 기준 **16.50초 → 2.43초(약 85% 단축)**라는 압도적인 성능 향상을 달성했습니다.
- [screener_benchmark_20260805_215007.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260805_215007.csv)

4. 단방향 윈도우 쿼리 최적화 (Reverse Windowing)
- 최적화 성과: `date ASC`로 재정렬하던 SQLite 오버헤드를 제거하고, 단일 방향(`rn ASC`) 윈도우 처리를 구현했습니다. 로컬 기준 절대 시간 차이는 **2.43초 → 2.42초**로 미미하지만, 1GB 서버 환경에서의 치명적인 메모리 스왑(Bi-directional Sorting 오버헤드)을 원천 차단하는 아키텍처적 완성도를 달성했습니다.
- [screener_benchmark_20260805_215923.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260805_215923.csv)

5. 인메모리 MA 엔진 도입 전 (로컬 베이스라인 재측정)
- 참고: 현재 파이썬 MA 엔진 도입 직전에 측정한 과거 로컬 성능입니다. 분봉 윈도우 풀스캔 시 약 2.9초가 소요됐습니다.
- [screener_benchmark_20260808_215546.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260808_215546.csv)

6. 순수 파이썬 인메모리 MA 엔진 전면 적용
- 최적화 성과: 무거운 SQLite 윈도우 함수 연산을 완전히 덜어내고, 파이썬 객체 기반의 O(1) 캐시와 전용 메모리 MA 테이블을 구축한 최종 벤치마크 결과입니다. 가장 무거운 분봉 윈도우 풀스캔 쿼리(Light 2, 4) 기준 **2.9초 → 1.4초(약 50% 단축)**로 극적인 성능 향상을 보였으며 물리 디스크 I/O를 원천 차단했습니다.
- [screener_benchmark_20260808_222427.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260808_222427.csv)
