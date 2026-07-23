# 배포 및 CI/CD 아키텍처 명세서 (CI/CD Specs)

본 문서는 Trading Server의 GitHub Actions 기반 자동화 파이프라인과 Docker 컨테이너 오케스트레이션 구조를 정의합니다.

## 1. 파이프라인 개요 (Pipeline Overview)
본 프로젝트는 **1개의 수동 트리거(Setup) 워크플로우**와 **1개의 자동 트리거(Deploy) 워크플로우**로 분리되어 완벽한 CD(Continuous Deployment)를 달성합니다.

### 1-A. 초기 서버 세팅 (Setup Server & SSL)
- **파일**: `.github/workflows/setup-server.yml`
- **트리거**: 개발자가 GitHub Actions 탭에서 수동 실행 (`workflow_dispatch`)
- **목적**: 
  1. OCI 서버에 배포 디렉토리(`~/Trading`)와 데이터 디렉토리(`~/Trading/data`) 생성.
  2. 사용자가 입력한 Domain, Email 및 GitHub Secrets(KIS API 등)를 바탕으로 **`.env`와 `kis_devlp.yaml` 파일을 동적으로 자동 생성**. (보안상 도커 이미지에 설정 파일이 포함되지 않는 문제 해결)
  3. `init-cert.sh` 스크립트를 실행하여 Nginx 구동에 필요한 Let's Encrypt SSL 인증서 최초 발급.

### 1-B. 메인 배포 파이프라인 (Automated Deploy)
- **파일**: `.github/workflows/deploy.yml`
- **트리거**: `main` 브랜치에 Push 발생 시 자동 실행
- **목적**:
  1. FastAPI 코드를 포함한 최신 Docker 이미지 빌드 및 GHCR 푸시.
  2. 서버(OCI)에 접속하여 변경된 `docker-compose.yml`, `.nginx/` 덮어쓰기.
  3. 최신 GitHub Secrets를 반영하여 서버의 **`kis_devlp.yaml`을 최신화(재생성)**.
  4. 최신 이미지 Pull 후 `docker compose up -d` 실행. (이때 새로 만들어진 설정 파일과 인증서를 볼륨 마운트로 자동으로 물고 올라감)

---

## 2. Docker Compose 아키텍처
**파일**: `docker-compose.yml`

| 서비스명 | 역할 | 포트 | 주요 마운트(Volumes) |
|---|---|---|---|
| `backend` | FastAPI 애플리케이션 및 스케줄러 구동 | - | `./data:/app/data` (DB 보존), `./.env:/app/.env` |
| `nginx` | 리버스 프록시 및 HTTPS 라우팅 | 80, 443 | `.nginx/conf.d`, `.nginx/certbot` (SSL 인증서) |
| `certbot` | 12시간마다 백그라운드에서 인증서 갱신 시도 | - | `.nginx/certbot` (Nginx와 공유) |

### 2-A. SQLite 영속성 및 마운트 전략 (중요)
- 로컬 개발 환경과 달리, OCI 서버의 `~/Trading` 폴더에는 파이썬 소스코드(`app/`)가 존재하지 않습니다(소스코드는 이미지 내부에 패키징됨).
- SQLite WAL 모드의 임시 파일들(`.db-wal`, `.db-shm`)이 휘발되어 DB가 손상되는 것을 막기 위해, 파일 단위 단일 마운트가 아닌 **디렉토리 단위 마운트(`./data:/app/data`)**를 강제합니다.
- 백엔드는 환경 변수 `SQLITE_DB_PATH=/app/data/trading.db`를 읽어 해당 마운트된 안전한 폴더에 DB를 보관합니다.

---

## 3. 리버스 프록시 (Nginx & SSL)
**파일**: `.nginx/conf.d/default.conf.template`
- HTTP(80)로 들어오는 트래픽은 모두 HTTPS(443)로 강제 리다이렉트(301)됩니다.
- 단, `.well-known/acme-challenge/` 경로는 예외 처리하여 Certbot의 도메인 소유권 검증 통신이 80포트를 통해 원활하게 이루어지도록 합니다.
- 환경 변수(`${DOMAIN}`)는 Nginx 컨테이너의 내장 템플릿 엔진(`envsubst`)에 의해 자동으로 실제 도메인으로 치환됩니다.

---

## 4. OCI 1GB 맞춤형 안전 배포 원칙 (Robust Deployment)
1GB RAM 환경에서의 메모리 고갈(OOM) 방지와 인프라 안정성을 위해, CI/CD 스크립트(.github/workflows)는 다음의 보수적인 원칙을 강제합니다. (관련: ADR-009)
1. **명시적 셧다운 (Down before Up)**: 무중단 배포를 시도하지 않습니다. 리소스 충돌 방지를 위해 `docker compose down`으로 기존 컨테이너를 완벽히 내린 후 새 이미지를 Pull하고 구동(`up -d`)합니다.
2. **Fail-Fast (`set -e`)**: 쉘 스크립트 실행 중 로그인 실패, 파일 생성 에러 등 단 하나의 명령어라도 실패하면 즉시 배포 프로세스를 중단시켜 깡통 컨테이너가 배포되는 것을 막습니다.
3. **환경 변수 파일(.env) 존재 검증**: 앱이 참조하는 파일이 디렉토리로 잘못 마운트되어 앱이 크래시되는 것을 막기 위해, 배포 전에 반드시 파일 존재 유무를 확인(`test -f .env`)합니다.
