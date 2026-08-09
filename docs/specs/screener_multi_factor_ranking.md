# Spec: Screener Multi-Factor Ranking System

## Objective
스크리너 엔진을 개편하여 기존의 '단순 통과 여부(True/False)'만 필터링하는 구조(Set 교집합)에서 **'다중 지표 랭킹(Multi-Factor Ranking)'** 시스템으로 진화시킵니다. 
각 필터 연산 시 종목의 통과 여부뿐만 아니라 **'조건 부합 강도를 나타내는 원본 지표 값(Float)'**을 추출하여 누적 전달합니다. 이를 통해 트레이더는 검색된 종목들 중 "어떤 종목이 조건에 가장 완벽하게 부합하는가"를 수치로 비교하고, 프론트엔드에서 원하는 지표를 기준으로 동적 정렬할 수 있습니다.

## Tech Stack
- Python >= 3.12
- FastAPI
- SQLite (In-Memory `daily_ma`, `minute_ma`)

## Commands
- **Backend Dev Server**: `uv run fastapi dev app/main.py`
- **Lint & Formatting**: `uv run ruff check . --fix && uv run ruff format .`
- **Benchmark**: `uv run python scripts/benchmark_screener.py`

## Project Structure
- `app/schemas/screener.py`: SSE 응답 및 파이프라인 반환 스키마 구조
- `app/services/screener_service.py`: 스크리너 엔진의 집합론 교집합 로직 및 SQLite Push-down 쿼리 생성
- `app/routes/screener.py`: API 엔드포인트

## Code Style
메모리 폭발(1GB RAM 환경)을 막기 위해 무거운 Pandas나 리스트 객체를 지양하고, 교집합 연산에 최적화된 딕셔너리 구조(`Dict[str, Dict[str, float]]`)를 사용합니다.

```python
# 기존 (Set 기반): 
# return {"005930", "000660"}

# 변경 (Dict 기반): 
# return {
#     "005930": {"ma_convergence_point_h3c": 0.3},
#     "000660": {"ma_convergence_point_h3c": 1.2}
# }

# 교집합(Intersection) 예시:
merged_dict = {}
for ticker, scores in dict_a.items():
    if ticker in dict_b:
        merged_dict[ticker] = scores | dict_b[ticker]
```

## Testing Strategy
- **수동 통합 테스트**: 기존에 작성된 `scripts/benchmark_screener.py`를 실행하여 딕셔너리 병합 로직 변환 이후에도 타임아웃(Timeout)이나 성능 저하 없이 잘 통과하는지 확인합니다.
- **결과 무결성 검증**: Swagger UI (`/docs`) 또는 cURL을 통해 `POST /api/screener/run` 호출 후, SSE 응답 스트림의 `complete` 이벤트에 `filter_values` 객체가 올바른 Float 값으로 삽입되어 반환되는지 확인합니다.

## Boundaries
- **Always**: SQLite `MAX()`, `MIN()` 등의 쿼리에서 발생하는 0으로 나누기 에러(Divide by Zero)를 방지하기 위해 `NULLIF`를 철저히 사용합니다.
- **Ask first**: 성능 문제로 인해 파이썬 단에서의 교집합(Dictionary Intersection) 로직을 변경해야 할 경우.
- **Never**: OOM(Out of Memory)을 유발할 수 있는 Pandas DataFrame으로의 전체 맵핑은 절대 사용하지 않습니다.

## Success Criteria
1. **Float 값 추출 완수**: 
   - `ma_convergence_consolidation` & `point`: 오차율 % (오름차순 기준)
   - `ma_alignment`: 이격도 편차율 % (오름차순 기준)
   - `ma_cross`: 단기선과 장기선의 차이 폭 % (내림차순 기준)
2. **파이프라인 병합(Merge)**: 기존 `Set` 교집합 로직이 `Dict` 교집합으로 완벽히 치환되며, 여러 지표가 안전하게 누적(`|` 연산)되어야 합니다.
3. **최종 응답 스키마 변경**: 클라이언트 수신 SSE 포맷의 `items` 안에 각 종목별 지표 값이 포함된 `filter_values: dict[str, float]`가 반환되어야 합니다.

## Open Questions
- 프론트엔드가 결과를 수신할 때 각 Float 값의 정렬 방향(오름차순/내림차순)을 동적으로 인지해야 할까요? (아니면 백엔드에서 통일된 정규화(Normalization) 처리를 해주는 것이 좋을까요?)
