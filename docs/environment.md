# 환경 설정과 로컬 실행

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

## 백엔드 실행

```powershell
uv sync
uv run fastapi dev app/main.py
```

로컬에서도 시작 과정에서 KIS 인증을 수행한다. 유효한 설정과 토큰 캐시가 없으면 앱이 기동하지 않을 수 있다.

## 프론트엔드 실행

```powershell
cd web
npm ci
$env:NEXT_PUBLIC_API_URL = "http://localhost:8000"
npm run dev
```

백엔드 CORS에는 localhost:3000과 현재 Vercel origin이 등록돼 있다. 다른 origin을 사용할 때는 CORS 정책을 명시적으로 갱신한다.

## 비밀정보

다음 파일은 Git에 커밋하지 않는다.

- `.env`
- `kis_devlp.yaml`
- `KIS20*` 토큰 캐시
- `*.db`, `data/`

설정 예시를 문서에 쓸 때도 실제 앱 키, 시크릿, 계좌번호, 토큰을 넣지 않는다.
