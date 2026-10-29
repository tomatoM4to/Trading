# Documentation Map

문서는 **작업 계약 → 현재 구조 → 주제별 결정 → 검증 근거** 순서로 읽는다. 구현의 최종 근거는 코드이며, 이 디렉터리는 왜 그 구조를 선택했는지와 어떻게 확인할지를 연결한다.

## Start Here

1. 실행하려면 [루트 README](../README.md)와 [환경 설정](environment.md).
2. 수정하려면 [AGENTS.md](../AGENTS.md)와 [아키텍처](architecture.md).
3. 성능 개선 과정을 보려면 [벤치마크](benchmark.md). 원본 CSV와 측정 조건까지 함께 확인한다.
4. 검증·배포하려면 [운영과 검증](operations.md), [배포](deployment.md).

## Topic Map

| 주제 | 문서에 남기는 내용 | 구현 진입점 |
|---|---|---|
| [Architecture](architecture.md) | 책임 경계·데이터 흐름·구조 선택 | [main](../app/main.py), [core](../app/core/) |
| [Database](database.md) | 정본·메모리 수명·MA 재구축 계약 | [database](../app/core/database.py), [MA](../app/core/ma_calculator.py) |
| [KIS Integration](kis-integration.md) | 인증·전역 큐·호출 제한 | [auth](../app/core/kis_auth.py), [fetch](../app/core/kis_fetch.py) |
| [Scheduler](scheduler.md) | 수집 순서·부트스트랩·GC 경계 | [scheduler](../app/core/scheduler.py), [tasks](../app/tasks/) |
| [Screener](screener.md) | AST 의미론·후보 축소·SSE | [service](../app/services/screener_service.py), [schema](../app/schemas/screener.py) |
| [API](api.md) | HTTP 경계·인증·부수 효과 | [routes](../app/routes/), [schemas](../app/schemas/) |
| [Frontend](frontend.md) | 필터·차트 데이터 흐름·타입 계약 | [web](../web/), [작업 규칙](../web/AGENTS.md) |
| [Environment](environment.md) | 로컬 설정·자격 증명·실행 | [pyproject](../pyproject.toml), [package](../web/package.json) |
| [Deployment](deployment.md) | 배포 절차·중단·미구현 품질 게이트 | [workflows](../.github/workflows/), [Compose](../docker-compose.yml) |
| [Operations](operations.md) | 운영 점검·안전한 검증·장애 대응 | [dependencies](../app/core/dependencies.py), [tests](../tests/) |
| [Benchmark](benchmark.md) | 현재 판단·개선 기록·측정 조건·원본 | [측정 스크립트](../scripts/benchmark_screener.py), [원본 CSV](benchmark-result/) |

## Maintenance

- 함수·상수·필드 전체 목록을 여러 문서에 복제하지 않는다. 세부 계약은 소스로 연결한다.
- 결정의 배경·대안·한계는 해당 주제에 남긴다. 별도 ADR을 만들지 않는다.
- 측정 기록은 목적, 조건, 결과, 결정, 한계, 원본 경로를 함께 남긴다.
- 과거 브랜치의 검증 자산은 출처 커밋을 고정한다. 현재 main에 반영된 것처럼 설명하지 않는다.
- 문서·코드·측정이 충돌하면 근거와 미확인 부분을 분리한다. 재실행하지 않은 측정에 새 검증 날짜를 붙이지 않는다.
