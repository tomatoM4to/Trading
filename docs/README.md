# 프로젝트 문서 지도

이 디렉터리는 현재 코드베이스의 동작을 설명한다. 과거 결정의 연대기보다 현재 구현 계약과 운영 경계를 우선한다. 동작이 바뀌면 코드 변경과 같은 작업에서 관련 문서를 함께 갱신한다.

| 문서 | 내용 | 주요 소스 |
|---|---|---|
| [architecture.md](architecture.md) | 전체 구성, 시작·종료 흐름, 모듈 경계 | `app/main.py`, `app/core/`, `web/` |
| [database.md](database.md) | 메모리/디스크 DB, 스키마, 연결 수명주기 | `app/core/database.py`, `app/core/ma_calculator.py` |
| [kis-integration.md](kis-integration.md) | 인증, 전역 큐, HTTP 호출 규칙 | `app/core/kis_auth.py`, `app/core/kis_fetch.py` |
| [scheduler.md](scheduler.md) | 예약 작업, 수집기, 부트스트랩, GC | `app/core/scheduler.py`, `app/tasks/` |
| [screener.md](screener.md) | AST, 비용 정렬, 필터, SSE | `app/services/screener_service.py` |
| [api.md](api.md) | FastAPI 엔드포인트와 응답 계약 | `app/routes/`, `app/schemas/` |
| [frontend.md](frontend.md) | Next.js 화면, 차트 집계, SSE 소비 | `web/app/`, `web/components/`, `web/lib/` |
| [environment.md](environment.md) | 설정 파일과 로컬 실행 | `.env`, `kis_devlp.yaml`, `pyproject.toml` |
| [deployment.md](deployment.md) | 이미지 빌드, 배포, Nginx, SSL | `Dockerfile`, `docker-compose.yml`, `.github/workflows/` |
| [operations.md](operations.md) | 상태 확인, 수동 작업, 검증과 알려진 위험 | `/health`, `/admin/*` |

## 문서 사용 원칙

1. `AGENTS.md`에서 전역 불변 원칙을 확인한다.
2. 현재 작업과 관련된 문서 한두 개만 읽는다.
3. 문서의 주요 소스 파일에서 현재 구현을 확인한다.
4. 코드와 문서가 충돌하면 코드를 현재 상태의 근거로 삼고 충돌을 보고한다.
5. 새로 비싼 결정을 내릴 때는 별도 ADR을 자동 생성하지 말고, 우선 해당 기능 문서의 설계 근거와 제약을 갱신한다.
