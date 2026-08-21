# 스크리너 엔진

## 요청 모델

`POST /api/screener/run`은 다음 형태의 AST를 받는다.

```json
{
  "filters": [
    {
      "id": "filter-1",
      "type": "ma_alignment",
      "params": {
        "lines": ["ma_daily_5", "ma_daily_20"],
        "duration": 3
      }
    }
  ],
  "operations": []
}
```

`operations`의 길이는 항상 `filters - 1`이어야 하며 값은 `AND` 또는 `OR`이다. 현재 `FilterNode.params`는 `dict[str, Any]`이므로 각 handler가 자기 파라미터의 타입과 범위를 검증할 책임이 있다.

## 파이프라인 의미론

1. OR을 기준으로 요청을 여러 AND 체인으로 나눈다.
2. 각 AND 체인은 추정 비용이 낮은 필터부터 실행한다.
3. 체인 안에서는 이전 결과의 ticker만 다음 필터에 전달한다.
4. 필터 결과는 `dict[str, dict[str, float]]`로 유지한다.
5. AND 교집합은 ticker를 기준으로 병합하고 OR 체인은 합집합한다.
6. 마지막에 종목 이름, 시장, 최근 가격·거래대금·등락률을 보강한다.

전 종목 OHLCV를 Pandas로 올리지 않는다. 후보 축소는 SQL `WHERE ticker IN (...)`과 파이썬 딕셔너리 교집합을 사용한다.

## 지원 필터

| type | 핵심 파라미터 | 데이터 원천 |
|---|---|---|
| `ma_alignment` | `lines`, `duration` | `daily_ma` 또는 `minute_ma` |
| `ma_cross` | `short_line`, `long_line`, `direction`, `within` | MA DB |
| `ma_convergence_consolidation` | `lines`, `threshold`, `duration` | MA DB |
| `ma_convergence_point` | `lines`, `threshold`, `within` | MA DB |
| `foreign_net_buy_rank` | `limit` | KIS 랭킹 API |
| `inst_net_buy_rank` | `limit` | KIS 랭킹 API |
| `disparity_value` | `line`, `threshold`, `direction` | OHLCV + attached MA DB |
| `volume_peak_breakout` | `lookback` | 일봉 또는 분봉 OHLCV |

허용 MA 기간은 `5, 10, 20, 60, 120, 200`이다. 컬럼명은 `_validate_ma_line()`을 통과한 값만 SQL에 사용한다. 기간 값은 일봉 최대 300, 분봉 최대 390 범위에서 정수로 검증한다.

## 비용 정렬

- 투자자 랭킹: 비용 0으로 먼저 실행해 최대 30개 후보로 축소
- 이격도·거래량 피크: 고정 저비용
- MA 계열: 기간 × 선 개수 × 시간 프레임 가중치
- 알 수 없는 필터: 가장 높은 기본 비용

정렬은 AND 내부에서만 수행하므로 요청의 논리 결과를 바꾸지 않는다.

## SSE 계약

응답 Content-Type은 `text/event-stream`이며 각 메시지는 JSON을 `data:`에 담는다.

| type | 필드 | 의미 |
|---|---|---|
| `start` | `filter_id` | 해당 필터 실행 시작 |
| `progress` | `filter_id`, `remaining` | 필터 완료와 남은 후보 수 |
| `complete` | `items` | 종목 정보와 `filter_values`를 포함한 최종 결과 |
| `error` | `message` | 파이프라인 내부 오류 |

SSE generator 내부 오류는 HTTP 상태를 바꾸지 않고 `error` 이벤트로 전달된다. 프론트엔드는 complete/error에서 AbortController로 스트림을 종료한다.

## 입력 안전 규칙

- 식별자는 정적 화이트리스트만 허용한다.
- 숫자는 `int` 또는 유한한 `float`로 변환한 뒤 범위를 확인한다.
- 값은 SQL placeholder로 바인딩한다.
- direction, lookback과 filter type은 고정 집합으로 검증한다.
- `limit`은 KIS 반환 한도 30을 넘지 않게 제한한다.

수렴 임계값은 0~100, 이격도 임계값은 0~1000 범위의 유한한 숫자만 허용하고 SQL placeholder로 바인딩한다. 투자자 랭킹 limit은 1~30 범위의 정수만 허용한다. 일봉 여부는 MA 컬럼명으로 정규화하기 전 요청 식별자에서 판별한다.

회귀 테스트는 `tests/test_regressions.py`에서 임계값 주입 방지, 범위 검증, 일봉 판별과 실제 수렴 쿼리 실행을 확인한다. AST AND/OR 의미론 전체에 대한 회귀 테스트는 아직 없다.
