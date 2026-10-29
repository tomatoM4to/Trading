# 벤치마크 하네스와 재현

[벤치마크 진입점](../benchmark.md) · [보존 결과](results.md)

## 구현 경계

| 항목 | main 기준 | dev 개선판 |
|---|---|---|
| 구성 | 5 Light + 5 Heavy | 7 Light + 5 Heavy |
| Light | 짧은 MA 조건, 랭킹 AND 포함 | 5~60봉 탐색, 이격도·거래량 돌파·OR 포함 |
| Heavy | 랭킹·AND로 후보가 먼저 줄어들 수 있음 | 랭킹·AND 없음, 장기 단독 스캔 및 OR |
| SSE `error` | 명시적 실패 처리 없음 | `BenchmarkStreamError` 발생 |
| `complete` 없이 EOF | `Success`, 0건으로 남을 수 있음 | 실패 처리 |
| 자동 계약 테스트 | 전용 파일 없음 | `tests/test_benchmark_screener.py` |
| 기본 대상 | `http://127.0.0.1:8000` | 당시 운영 서버 주소 |

출처:
- [main 실행기](https://github.com/tomatoM4to/Trading/blob/652bb24da07e35c07539997d9faa10413a414eba/scripts/benchmark_screener.py)
- [dev 실행기](https://github.com/tomatoM4to/Trading/blob/b8e94dd88064fee47895362b736d49c0cd4b4cf2/scripts/benchmark_screener.py)
- [dev 계약·스트림 테스트](https://github.com/tomatoM4to/Trading/blob/b8e94dd88064fee47895362b736d49c0cd4b4cf2/tests/test_benchmark_screener.py)

두 실행기 모두 시나리오를 순차로 한 번씩 수행한다. 요청 전후의 `time.perf_counter()` 차이를 소수점 셋째 자리로 저장하며, HTTP·네트워크·서버·SSE 수신 시간이 함께 포함된다. `requests`의 `timeout=120`을 전체 실행의 정확한 120초 제한으로 해석하지 않는다. 프록시가 먼저 504를 반환할 수도 있다.

두 버전 모두 CSV 행에 실패가 있어도 마지막에 `Benchmark completed successfully.`를 출력할 수 있다. 종료 문구나 종료 코드만으로 통과를 판정하지 말고 각 행의 `Status`와 완료 근거를 확인한다. 개선판도 결과 정답 집합, 반복 통계, 자원 사용량을 검증하는 하네스는 아니다.

## main에서 재현할 때

운영 서버를 자동으로 선택하지 않는다. 아래 명령은 **이미 준비된 로컬 테스트 서버**를 대상으로 한다. 앱 시작 자체가 부트스트랩·KIS 호출을 일으킬 수 있으므로 [환경](../environment.md)과 [운영·검증](../operations.md)을 먼저 확인한다.

```bash
uv run python scripts/benchmark_screener.py --host http://127.0.0.1:8000
```

1. 서버와 실행기의 커밋을 기록한다. `/health` 응답만으로 DB·MA 준비 완료를 판단하지 않는다.
2. DB 적재 범위, 최신 캔들 시각, 종목 수, 시스템 가드 상태를 확인한다.
3. 실행 후 현재 디렉터리의 `screener_benchmark_YYYYMMDD_HHMMSS.csv`를 확인한다.
4. `Status`와 SSE 로그를 대조한다. main 실행기의 `Success`만으로 완료를 보장할 수 없다.
5. 조건이 동일한 반복 결과만 묶는다. 단일 실행을 평균·p95·최대 처리량으로 표현하지 않는다.

위 명령은 현재 main의 **기존 10개**를 실행한다. dev 결과 표의 12개를 재현하는 명령으로 소개하지 않는다. 이번 문서 변경에서는 실행하지 않았다.

## 개선판 검증 자산

개선판의 10개 테스트는 다음을 확인한다.

- 7 Light + 5 Heavy 구성과 전체 payload의 `ScreenerRequest` 계약.
- 이격도·거래량 돌파 단독 사례, Light 탐색 범위, 2·3분기 OR의 존재.
- Heavy에 투자자 랭킹과 AND가 없는지.
- SSE 완료의 개수 반환, SSE 오류, 완료 없는 종료의 실패 처리.

이 테스트는 main에 아직 없다. 개선판을 가져오는 별도 코드 작업에서 실행할 명령은 다음과 같다.

```bash
uv run python -m unittest discover -s tests -p 'test_benchmark_screener.py' -v
```

이는 네트워크 부하 측정을 대신하지 않으며, 테스트 통과도 운영 서버 성능을 보증하지 않는다. 이번 정리는 테스트 소스를 읽었을 뿐 dev 테스트를 실행하거나 main으로 이식하지 않았다.

## 측정 기록 양식

새 결과 옆에는 아래 정보를 함께 남긴다. 알 수 없는 값은 추정으로 채우지 않고 `미기록`으로 표시한다.

```text
목적 / 비교할 변경:
서버 커밋 / 하네스 커밋:
시나리오 이름 및 payload 또는 해시:
클라이언트·서버 환경 / 측정 시각·타임존:
DB 스냅샷 식별자 / 종목·행 수 / 최신 캔들 / MA 준비 상태:
워밍업 / 반복 횟수 / 다른 수집 작업의 실행 여부:
원시 CSV / SSE 로그 / 실패·미완료:
요약 통계 / 해석 가능한 범위 / 남은 한계:
```

계좌·API 키·토큰·DB 파일 자체를 기록에 첨부하지 않는다. 메모리·스왑·I/O 개선을 주장하려면 별도 계측 방법과 로그가 필요하다.
