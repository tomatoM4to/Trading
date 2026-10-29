# Trading Server & Dashboard

KIS OpenAPI로 국내 주식의 일봉·분봉을 수집하고, 로컬 SQLite 데이터로 돌파 전략 스크리닝과 차트를 제공한다. FastAPI 백엔드와 Next.js 대시보드로 구성되며, 운영 목표 환경은 Oracle Cloud Free Tier의 1 OCPU·1GB RAM이다.

## Current State

- 종목 마스터·OHLCV는 디스크 SQLite(WAL), 반복 조회용 이동평균은 별도 Shared In-Memory DB에 둔다.
- 스크리너는 후보 종목을 단계적으로 줄이고 SSE로 진행 상황과 결과를 전달한다.
- 프론트엔드는 차트와 필터 조합 UI를 제공한다. 이 저장소의 현재 HTTP 경로는 데이터 수집·조회·스크리닝 중심이다.
- 성능 개선 과정과 원본 측정 자료는 [벤치마크](docs/benchmark.md)에서 읽는다. 과거 측정값은 현재 운영 성능 보장이 아니다.

## Quick Start

Python 3.12 이상, uv, Node.js와 npm이 필요하다. 저장소 루트에서 실행한다.

```powershell
git clone https://github.com/tomatoM4to/Trading.git
cd Trading
uv sync --locked
```

[환경 설정](docs/environment.md)에 따라 `.env`와 `kis_devlp.yaml`을 로컬에 준비한다. 개발 시 `DEBUG=True`, `SCHED=False`로 시작한다. **이 설정도 오프라인 모드는 아니다.** 앱 시작 시 KIS 인증을 수행하며, 기존 OHLCV로 MA DB를 재구축한다. 빈 DB의 전체 수집은 별도 부트스트랩이 필요하다.

```powershell
uv run fastapi dev app/main.py
```

다른 터미널에서 프론트엔드를 시작한다.

```powershell
cd web
npm ci
$env:NEXT_PUBLIC_API_URL = "http://localhost:8000"
npm run dev
```

- 대시보드: http://localhost:3000
- 백엔드 상태: http://localhost:8000/health
- API 스키마: http://localhost:8000/docs

`/health`는 프로세스 응답만 확인한다. 데이터 적재·MA 준비 여부는 [운영 점검](docs/operations.md)을 따른다. 관리자 API는 별도 `ADMIN_API_KEY` 설정과 `X-Admin-Key` 헤더가 필요하다.

## Verification

```powershell
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v

cd web
npm run lint
npx tsc --noEmit
npm run build
```

회귀 테스트, 실제 KIS 호출이 필요한 통합 검증, 성능 측정은 서로 다른 절차다. 실행 조건과 결과 기록 방법은 [운영과 검증](docs/operations.md), 성능 측정은 [벤치마크](docs/benchmark.md)를 따른다.

## Documentation

| 목적 | 문서 |
|---|---|
| 작업 규칙 | [AGENTS.md](AGENTS.md) |
| 전체 문서 지도 | [docs/README.md](docs/README.md) |
| 구조와 설계 판단 | [architecture](docs/architecture.md) |
| 성능 개선 과정·측정 근거 | [benchmark](docs/benchmark.md) |
| 설정 / 배포 / 운영 | [environment](docs/environment.md), [deployment](docs/deployment.md), [operations](docs/operations.md) |

## Deployment

배포 절차와 필요한 GitHub Secrets는 [배포 문서](docs/deployment.md)에 모았다. `main` push는 운영 배포 워크플로를 실행한다. 현재 Compose 배포에는 서비스 중단 구간이 있고 자동 롤백·배포 전 테스트 게이트가 없으므로 문서 PR도 병합 전에 배포 영향을 확인한다.
