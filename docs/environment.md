# 환경 설정과 로컬 실행

## Current Decision

개발 설정은 예약 수집을 끌 수 있지만 KIS 인증까지 끄지는 않는다. 실제 자격 증명·계좌·토큰은 저장소와 브라우저에 남기지 않는다.

- 구현 근거: [main.py](../app/main.py), [kis_auth.py](../app/core/kis_auth.py), [database.py](../app/core/database.py), [dependencies.py](../app/core/dependencies.py)
- 함께 읽기: [빠른 실행](../README.md), [배포](deployment.md), [운영](operations.md)

## 요구 사항

- Python 3.12 이상
- uv
- Node.js와 npm
- KIS 실전투자 API 자격 증명

## `.env`

| 변수 | 기본값 | 역할 |
|---|---|---|
| `DEBUG` | `False` | `True`면 캐시 토큰 재사용, `False`면 시작 시 강제 재발급 |
| `SCHED` | `False` | 스케줄러와 전체 부트스트랩 실행 여부 |
| `LOG_LEVEL` | 로깅 구현 기본값 | 애플리케이션 로그 레벨 |
| `SQLITE_DB_PATH` | `data/trading.db` | 영속 DB 파일 경로 override |
| `ADMIN_API_KEY` | 없음 | `/admin/*` 요청의 `X-Admin-Key`와 비교할 관리자 비밀값. 미설정 시 관리자 API 503 |
| `DOMAIN` | 없음 | Docker Compose Nginx 템플릿 도메인 |
| `EMAIL` | 없음 | 초기 인증서 발급 연락처 |

`DEBUG`와 `SCHED`는 독립적이다. `DEBUG`는 인증 정책만, `SCHED`는 예약 작업과 부트스트랩만 제어한다.

권장 로컬 설정:

```dotenv
DEBUG=True
SCHED=False
LOG_LEVEL=DEBUG
```

운영 설정:

```dotenv
DEBUG=False
SCHED=True
LOG_LEVEL=INFO
ADMIN_API_KEY=충분히-긴-무작위-비밀값
```

## `kis_devlp.yaml`

현재 애플리케이션에 필요한 핵심 값은 다음과 같다.

```yaml
my_app: "실전 앱 키"
my_sec: "실전 앱 시크릿"
my_htsid: "HTS ID"
my_acct_stock: "8자리 계좌번호"
my_prod: "01"
prod: "https://openapi.koreainvestment.com:9443"
ops: "ws://ops.koreainvestment.com:21000"
vps: "https://openapivts.koreainvestment.com:29443"
vops: "ws://ops.koreainvestment.com:31000"
my_token: ""
my_agent: "사용자 에이전트"
```

Pydantic 모델에는 일부 모의·선물 계좌 필드가 남아 있지만 현재 인증과 운영 경로는 실전 REST URL과 실전 자격 증명을 사용한다.

## 실행 경계

명령은 [루트 README](../README.md#quick-start)와 [프론트엔드 README](../web/README.md#run)를 따른다.

로컬에서도 시작 과정에서 KIS 인증을 수행한다. 유효한 설정과 토큰 캐시가 없으면 앱이 기동하지 않을 수 있다. `SCHED=False`는 예약 작업과 전체 수집 부트스트랩을 끄지만 기존 OHLCV로 MA를 재구축한다. 빈 DB를 자동으로 채우는 설정으로 오해하지 않는다.

백엔드 CORS에는 localhost:3000과 현재 Vercel origin이 등록돼 있다. 다른 origin은 [main.py](../app/main.py)의 정책을 함께 확인한다.

## 비밀정보

다음 파일은 Git에 커밋하지 않는다.

- `.env`
- `kis_devlp.yaml`
- `KIS20*` 토큰 캐시
- `*.db`, `data/`

설정 예시를 문서에 쓸 때도 실제 앱 키, 시크릿, 계좌번호, 토큰을 넣지 않는다.
