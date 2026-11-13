# Trading Server
KIS OpenAPI 기반 국내 주식 데이터 수집 및 기술적 분석 서비스입니다.

국내 약 2,400개 종목의 일봉·분봉 데이터를 수집하고, 로컬 SQLite를 기반으로 기술적 지표 계산, 조건 검색(Screener), 차트 조회를 제공합니다.

Oracle Cloud Free Tier의 **1 OCPU / 1GB RAM** 환경을 목표로 데이터 수집, 메모리 사용량, 쿼리 성능을 최적화했습니다.

## Tech Stack
| Layer | Technologies |
|---|---|
| Backend | Python 3.12+, FastAPI |
| Database | SQLite, WAL, Shared In-Memory |
| Scheduling | APScheduler, asyncio |
| Analysis | Pandas, SQL |
| Frontend | Next.js 16, React 19, TypeScript |
| Charts | Lightweight Charts |
| Infrastructure | Docker Compose, Nginx, GitHub Actions |
| Package Management | uv, npm |

## Getting Started
### Step 1. Clone & Sync
Python 3.12+, uv, Node.js 및 npm이 필요합니다.

```bash
git clone --recurse-submodules https://github.com/tomatoM4to/Trading.git
cd Trading
uv sync --locked
```

### Step 2. 환경 설정
프로젝트 루트에 `.env`와 `kis_devlp.yaml` 파일을 준비합니다.

**`.env`**

```dotenv
DEBUG=True
SCHED=False
LOG_LEVEL=DEBUG
ADMIN_API_KEY=your-local-admin-key
```

| Variable | Description |
|---|---|
| `DEBUG` | `True`: 유효한 KIS 토큰 캐시 재사용 / `False`: 서버 시작 시 토큰 강제 재발급 |
| `SCHED` | `True`: 정규 스케줄러 및 초기 데이터 복구 실행 / `False`: 스케줄러 비활성화, 기존 OHLCV로 MA DB 재구축 |
| `LOG_LEVEL` | 애플리케이션 로그 출력 수준 |
| `ADMIN_API_KEY` | 관리자 API 인증 키. `/admin/*` 요청 시 `X-Admin-Key` 헤더로 전달 |
| `SQLITE_DB_PATH` | SQLite 파일 경로 (선택 사항, 기본값: `data/trading.db`) |

> `DEBUG`와 `SCHED`는 독립적으로 동작합니다. `SCHED=False`는 오프라인 모드가 아니며, 서버 시작 시 KIS 인증이 수행됩니다. `ADMIN_API_KEY`가 설정되지 않으면 관리자 API는 503을 반환합니다.

**`kis_devlp.yaml`**

```yaml
# KIS Credentials
my_app: "실전투자 앱 키"
my_sec: "실전투자 앱 시크릿"
my_htsid: "HTS ID"
my_acct_stock: "계좌번호 앞 8자리"
my_prod: "01"

# KIS Endpoints
prod: "https://openapi.koreainvestment.com:9443"
ops: "ws://ops.koreainvestment.com:21000"
vps: "https://openapivts.koreainvestment.com:29443"
vops: "ws://ops.koreainvestment.com:31000"

my_token: ""
my_agent: "Mozilla/5.0"
```

> `my_app`, `my_sec`, `my_htsid`, `my_acct_stock`, `my_prod`에 실제 정보를 입력합니다. 나머지 설정은 기본값을 유지합니다. API 키, 계좌번호, 토큰 및 `.env` 파일은 Git에 커밋하지 않습니다.

### Step 3. Run
**Backend**

```bash
uv run fastapi dev app/main.py
```

**Frontend (별도 터미널)**

```bash
cd web
npm ci
npm run dev
```

기본 프론트엔드 API 주소는 `http://localhost:8000`이며, 필요하면 `NEXT_PUBLIC_API_URL`로 변경할 수 있습니다.

- Dashboard: http://localhost:3000
- Backend Health: http://localhost:8000/health
- API Documentation: http://localhost:8000/docs

> `/health`는 프로세스 응답 여부만 확인하며, 데이터 수집 및 이동평균 계산 완료를 보장하지 않습니다.

## Deployment Guide
### Step 1. GitHub Secrets 환경변수 세팅
GitHub 레포지토리의 **Settings → Secrets and variables → Actions**에서 다음 Repository secrets를 등록합니다.

**서버 및 인프라**

| Secret Name | 설명 | 예시 |
|---|---|---|
| `OCI_HOST` | Oracle Cloud 서버 공인 IP | `123.45.67.89` |
| `OCI_USERNAME` | 서버 SSH 사용자 계정 | `ubuntu` 또는 `opc` |
| `OCI_SSH_KEY` | 서버 접속용 SSH Private Key | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `CR_PAT` | GHCR 이미지 인증용 GitHub Personal Access Token | `ghp_xxxxxxxx...` |
| `DOMAIN` | Nginx에 사용할 도메인 | `api.example.com` |

**KIS API 정보**

| Secret Name | 설명 | 예시 |
|---|---|---|
| `KIS_MY_APP` | KIS 실전투자 App Key | `your-app-key` |
| `KIS_MY_SEC` | KIS 실전투자 App Secret | `your-app-secret` |
| `KIS_MY_HTSID` | KIS HTS 접속 ID | `your-hts-id` |
| `KIS_MY_ACCT_STOCK` | 주식 계좌번호 앞 8자리 | `12345678` |
| `KIS_MY_PROD` | 계좌 상품코드 뒤 2자리 | `01` |

> GitHub Actions는 등록된 Secrets를 사용하여 서버에 `.env` 및 `kis_devlp.yaml` 파일을 생성합니다. 현재 워크플로는 `ADMIN_API_KEY`를 자동 설정하지 않으므로, 운영 관리자 API 사용 시 서버의 `.env`에 별도로 설정해야 합니다.

### Step 2. 서버 초기 인프라 세팅 (최초 1회)
Docker 환경을 준비하고, 설정 파일 생성 및 HTTPS 인증서 발급을 수행합니다.

1. GitHub 레포지토리의 **Actions** 탭으로 이동합니다.
2. **🛠️ Setup Server & SSL** 워크플로를 선택합니다.
3. **Run workflow**를 클릭합니다.
4. 인증서 발급에 사용할 `Domain Name`과 `Email`을 입력하고 실행합니다.

> 서버의 `~/Trading` 디렉터리에 `.env`, `kis_devlp.yaml` 및 인프라 파일이 생성되고 SSL 인증서가 발급됩니다.

### Step 3. 메인 배포 (자동 실행)
초기 설정 이후에는 `main` 브랜치에 Push 또는 Merge 시 GitHub Actions가 자동 배포를 수행합니다.

1. Docker 이미지 빌드 및 GHCR 업로드
2. Oracle Cloud 서버에 배포 설정 반영
3. 최신 이미지 Pull 및 Docker Compose 재시작

> 현재 배포는 컨테이너 재시작 과정에서 일시적인 서비스 중단이 발생할 수 있습니다.

## Documentation
- [Architecture](docs/architecture.md)
- [Database](docs/database.md)
- [KIS Integration](docs/kis-integration.md)
- [Scheduler](docs/scheduler.md)
- [Strategy & Screener](docs/screener.md)
- [Benchmark](docs/benchmark.md)

개발 규칙과 검증 경계는 [AGENTS.md](AGENTS.md)를 참고합니다.