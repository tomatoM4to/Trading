# 스크리너 벤치마크

## 현재 측정기

`scripts/benchmark_screener.py`는 격리된 디스크 SQLite와 고유 MA 메모리 DB에서 고정 합성 데이터를 생성한다. 원격 서버와 KIS API를 호출하지 않는다. 이전 HTTP 측정기의 error/미완료 SSE를 Success로 기록할 수 있는 판정과 독립 기대값 부재를 제거했다. 기존 `--host` 옵션은 폐기했다.

```powershell
uv run --locked python scripts/benchmark_screener.py --tickers 64 --repeats 3
```

일봉 500개·분봉 590개를 종목별로 적재하고 실제 부트스트랩 MA 재구축을 실행한다. 종목의 절반은 상승, 절반은 하락 시계열이다. 실제 스크리너 SSE가 단 하나의 complete로 끝나고, 모든 기대 종목과 필터 값이 독립 산술 기준에 일치해야 시간과 성공을 기록한다. 오류·미완료·잘못된 빈 결과는 측정 실패다. 정확성 하네스와 별도 명령으로 유지하며, 전 종목 시계열을 하나의 DataFrame으로 복제하지 않는다.

`--tickers` 범위는 2..2400, `--repeats`는 1..20이다. 기본 64종목 측정을 운영 전체 규모의 성능으로 일반화하면 안 된다. 로그에는 처리 레코드, MA 보존 행, 준비 시간, 반복별 시간/성공·실패·검색 수, Python 프로세스 peak RSS가 포함된다. 준비 시간은 Fixture 생성·저장·MA 재구축 전체이고, RSS는 OS page cache를 제외한 프로세스 최고치다.

2026-11-13 Windows / Python 3.12.12 / SQLite 3.50.4 단일 실행: 64종목, 69,760 OHLCV행, daily_ma 19,264행, minute_ma 25,024행. 준비 1.543초, 3회 조회 0.0251..0.0262초, 매회 32종목과 전체 필터 값 일치, peak RSS 약 93.9MiB. CPU/메모리 제한이 없는 로컬 단기 측정이며 Linux 1 OCPU/1GB 결과가 아니다. 결과 JSON은 사용자 요청으로 제거하고 측정 조건과 요약만 보존했다.

위 Windows 기록 당시에는 Docker 엔진에 접근하지 못했다. 아래 후속 검증에서 제한 Linux 컨테이너를 실행했다. HTTP·외부 수급을 포함한 과거 CSV와 합성 로컬 결과는 동일 입력/환경이 아니므로 직접 비교하지 않는다.

## 잔여 결함 수정 전후 — 2026-11-13

기준선은 `6c6b4d5`, 수정본은 잔여 결함 작업 트리다. 같은 Python 3.12.12 / SQLite 3.40.1 / Linux Docker Desktop WSL2, `--cpus=1 --memory=1g --network=none --read-only`, 임시 tmpfs 768MiB에서 측정했다. 자격 증명·운영 볼륨은 사용하지 않았다. 운영 Oracle CPU·디스크와 동등한 환경은 아니다.

### 일봉 수집

`scripts/benchmark_collection.py --tickers 4`는 종목별 고정 500봉 최초 수집 → 신규 1봉 → 40번째 내부 행 삭제를 실행한다. 실제 Queue·0.1초 대기·HTTP 변환·SQLite·MA를 통과하고, 단계별 전체 OHLCV와 모든 보존 MA를 독립 분수 계산과 비교한다. Fake 전송 지연은 0이며, Queue 대기는 요청 제출→Fake 전송 시작의 합계다. 동시 대기를 합산하므로 벽시계 시간보다 클 수 있다.

| 시나리오 | 호출 수 전→후 | 실행시간 전→후(초) | Queue 대기 합계 전→후(초) | 결과 |
|---|---|---|---|---|
| 최초 500봉 × 4 | 20→20 | 1.955→1.970 | 7.134→7.183 | 2,000행·MA 일치 |
| 검증된 이력 + 1봉 | 20→4 | 2.047→0.395 | 7.481→0.916 | 2,004행·MA 일치 |
| 첫 페이지 밖 갭 복구 | 20→20 | 2.057→2.019 | 7.476→7.392 | 2,004행·MA 일치 |

Python peak RSS는 99.67→100.34MiB였다. 단일 짧은 측정이므로 미세한 시간·RSS 차이를 개선/회귀로 주장하지 않는다. 인증·깊은 검증 예산 실패는 Stage 2에서 별도 확인한다. 2,400종목의 수집 완료 시간은 실제 전송하지 않았고, 호출 간격만의 하한은 [scheduler.md](scheduler.md)에 산술값으로 구분했다.

### 2,400종목 스크리너

`scripts/benchmark_screener.py --tickers 2400 --repeats 3`의 동일 합성 입력이다. 일봉 1,200,000행 + 분봉 1,416,000행, 보존 MA 일봉 722,400행·분봉 938,400행이다. 조회마다 기대 1,200종목과 필터 값 전체가 일치했다.

| 측정 | 기준선 | 수정본 |
|---|---:|---:|
| Fixture 생성·저장·MA 구축(초) | 33.452 | 33.678 |
| 스크리너 3회(초) | 0.955 / 0.940 / 0.941 | 0.975 / 0.952 / 0.945 |
| Python peak RSS(MiB) | 272.67 | 279.23 |
| 수정본 cgroup 전체 peak(MiB) | 미측정 | 424.75 |

수정본 cgroup `memory.peak`는 445,378,560bytes로 tmpfs·page cache 등을 포함한다. 1GiB 제한에서 정상 종료했고 OOM은 없었다. 스레드 재구축과 원본 열 추가 후에도 제한 내 생존했지만, 단기 대표 쿼리 3회의 결과이며 장시간 누적·모든 heavy 필터 조합의 보장은 아니다. 기존 비용 정렬·후보 pushdown·short-circuit·MA 사전 계산은 유지했다.

재현은 [Docker 명령](testing.md#docker-linux-검증)을 따른다. `memory.peak`는 측정 Python 실행 뒤 같은 컨테이너에서 읽는다. 과거 서버 CSV와 이 표를 직접 비교하지 않는다.

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
