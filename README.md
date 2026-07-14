# Trading Server

KIS OpenAPI를 활용한 Zero-Latency Breakout(돌파) 전략 기반의 자동 매매 백엔드 시스템입니다.
Oracle Cloud Free Tier(1 OCPU / 1GB RAM)의 자원 제약을 극복하기 위해 SQLite WAL 모드와 고도의 백그라운드 스케줄러 최적화 기법을 적용했습니다.

---

## 🚀 배포 가이드 (Deployment Guide)

본 프로젝트는 GitHub Actions를 활용하여 **완전 자동화된 CI/CD 파이프라인**이 구축되어 있습니다. 
로컬 코드를 수동으로 서버에 전송할 필요 없이, 아래 순서에 따라 GitHub 설정만 완료하면 인프라 세팅부터 SSL 발급, 서비스 구동까지 자동으로 진행됩니다.

### Step 1. GitHub Secrets 환경변수 세팅 (가장 중요)
배포를 시작하기 전, GitHub 레포지토리의 **[Settings] -> [Secrets and variables] -> [Actions]** 로 이동하여 `Repository secrets`에 아래 변수들을 반드시 등록해주세요.

| Secret Name | 설명 | 예시 |
|---|---|---|
| **[서버 및 인프라]** |
| `OCI_HOST` | 배포할 오라클 클라우드(OCI) 서버의 공인 IP 주소 | `123.45.67.89` |
| `OCI_USERNAME` | 서버 접속용 SSH 사용자 계정명 | `ubuntu` (또는 `opc`) |
| `OCI_SSH_KEY` | 서버 접속에 사용할 SSH Private Key | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `CR_PAT` | 도커 이미지 푸시용 GitHub Personal Access Token | `ghp_xxxxxxxx...` |
| `DOMAIN` | 서버에 연결된 도메인 이름 (Nginx용) | `api.yourdomain.com` |
| **[KIS API 정보]** |
| `KIS_MY_APP` | KIS OpenAPI 실전투자 App Key | `PSuZZZOS...` |
| `KIS_MY_SEC` | KIS OpenAPI 실전투자 App Secret | `jkSniXR...` |
| `KIS_MY_HTSID` | 한국투자증권 HTS 접속 ID | `toM4to` |
| `KIS_MY_ACCT_STOCK` | 주식 계좌번호 앞 8자리 | `12345678` |
| `KIS_MY_PROD` | 계좌 상품코드 뒤 2자리 (종합계좌는 `01`) | `01` |

*(참고: 이 시크릿들은 깃허브 액션이 실행될 때 동적으로 서버에 `kis_devlp.yaml` 과 `.env` 파일을 안전하게 생성하는 데 사용되며, 절대로 코드에 하드코딩되어 노출되지 않습니다.)*

---

### Step 2. 서버 초기 인프라 세팅 (최초 1회 수동 실행)
도커 마운트를 위한 디렉토리를 생성하고, `.env` 환경변수 파일을 세팅한 뒤 HTTPS(SSL) 인증서를 최초 발급받는 작업입니다.

1. 깃허브 레포지토리 상단의 **[Actions]** 탭 클릭
2. 좌측 메뉴에서 **`🛠️ Setup Server & SSL`** 워크플로우 선택
3. 우측의 **[Run workflow]** 버튼 클릭
4. 인증서 발급에 사용할 `Domain Name`과 `Email`을 입력하고 실행!
   - ➔ 서버의 `~/Trading` 폴더에 `.env`와 인프라 파일들이 자동 배치되고 인증서 발급이 완료됩니다.

---

### Step 3. 메인 배포 (자동 실행)
초기 세팅(Step 2)이 끝났다면, 이제부터는 코드 개발에만 집중하시면 됩니다.

1. 로컬에서 코드를 수정하고 **`main` 브랜치에 Push** (또는 Pull Request Merge) 합니다.
2. 자동으로 메인 배포 워크플로우(`deploy.yml`)가 돌아갑니다.
3. 소스코드가 도커 이미지로 빌드되어 GHCR에 안전하게 보관되며, OCI 서버는 가장 최신 이미지를 다운받아 서버를 무중단(또는 짧은 다운타임) 재시작합니다.
4. **HTTPS(443)** 환경에서 동작하는 Zero-Latency API 서버가 켜집니다! 🎉

---

## 📚 관련 기술 문서
- 전체 파이프라인 및 Docker 구조: [`docs/cicd.md`](./docs/cicd.md)
- SQLite 영속성 마운트 전략 (ADR): [`docs/decisions/ADR-005-docker-sqlite-persistence-strategy.md`](./docs/decisions/ADR-005-docker-sqlite-persistence-strategy.md)
- 백그라운드 스케줄러 명세: [`docs/scheduler.md`](./docs/scheduler.md)
- DB 및 스키마 설계: [`docs/database.md`](./docs/database.md)