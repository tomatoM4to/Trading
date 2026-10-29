# 배포와 인프라

## Current Decision

백엔드는 Docker Compose로 단일 서버에 배포하고 프론트엔드는 별도로 운영한다. `main` push가 배포를 실행하므로 문서 변경도 병합 시 운영 재시작을 유발할 수 있다.

- 구현 근거: [Dockerfile](../Dockerfile), [Compose](../docker-compose.yml), [초기화](../.github/workflows/setup-server.yml), [배포](../.github/workflows/deploy.yml), [Nginx](../.nginx/conf.d/default.conf.template)
- 함께 읽기: [환경 설정](environment.md), [운영·복구](operations.md)

## 구성

| 컴포넌트 | 역할 |
|---|---|
| backend | FastAPI, 디스크 OHLCV SQLite와 MA 전용 메모리 SQLite |
| nginx | HTTP→HTTPS 전환과 backend reverse proxy |
| certbot | 12시간마다 인증서 갱신 시도 후 Nginx reload |
| GHCR | backend 이미지 저장소 |
| GitHub Actions | 서버 초기화와 main 배포 |

프론트엔드는 이 Compose 스택에 포함되지 않으며 별도 Vercel origin을 CORS에 허용하고 있다.

## 이미지

`Dockerfile`은 uv Python 3.12 builder에서 locked production dependency를 설치한 뒤 `python:3.12-slim-bookworm` 런타임으로 복사한다. 컨테이너 명령은 다음과 같다.

```text
fastapi run app/main.py --port 8000 --host 0.0.0.0
```

`data/`는 이미지가 아니라 호스트 volume으로 유지한다. `.env`와 `kis_devlp.yaml`도 read-only volume으로 주입한다.

## 서버 초기화

`.github/workflows/setup-server.yml`은 수동 실행한다.

1. Compose, Nginx 설정, 인증서 스크립트를 `~/Trading`에 복사한다.
2. GitHub Secrets로 `.env`와 `kis_devlp.yaml`을 생성한다.
3. `init-cert.sh`로 최초 Let's Encrypt 인증서를 발급한다.

### 사전 준비

저장소 **Settings → Secrets and variables → Actions**의 Repository secrets에 설정한다. 실제 값은 문서·커밋·로그에 남기지 않는다.

| Secret | 용도 |
|---|---|
| `OCI_HOST` | OCI 서버 공인 주소 |
| `OCI_USERNAME` | SSH 사용자 |
| `OCI_SSH_KEY` | 해당 서버 접속용 SSH 개인 키 |
| `DOMAIN` | 배포 시 Nginx에 적용할 도메인 |
| `CR_PAT` | GHCR 이미지 push 및 서버 pull 인증 |
| `KIS_MY_APP` | KIS 실전 App Key |
| `KIS_MY_SEC` | KIS 실전 App Secret |
| `KIS_MY_HTSID` | HTS ID |
| `KIS_MY_ACCT_STOCK` | 실전 주식 계좌 앞 8자리 |
| `KIS_MY_PROD` | 계좌 상품 코드. 워크플로 기본값 `01` |

처음에는 Actions의 **Setup Server & SSL**을 선택하고 도메인과 인증서 연락처 이메일을 입력해 실행한다. 초기화의 도메인은 workflow input, 이후 배포의 도메인은 `DOMAIN` Secret을 사용하므로 두 값이 일치해야 한다.

초기화 스크립트는 `.env`를 다시 작성하며 현재 `ADMIN_API_KEY`를 생성하지 않는다. 운영자는 서버 `.env`에 별도 관리자 키를 안전하게 설정하고, 초기화를 재실행했다면 키가 유지됐는지 확인한다. 키 미설정 시 관리자 API는 503으로 차단된다. 비밀값을 `NEXT_PUBLIC_*` 변수나 프론트엔드에 넣지 않는다.

## main 배포

`.github/workflows/deploy.yml`은 main push에서 실행된다.

1. checkout
2. SHA·branch·latest 태그로 이미지 build/push
3. 인프라 파일을 서버에 복사
4. 서버의 `.env` 존재 확인
5. KIS Secrets로 `kis_devlp.yaml` 재생성
6. `docker compose down`, pull, `up -d`
7. 미사용 이미지 prune

현재 `down`과 `up` 사이에 서비스 중단이 있으며 자동 롤백은 없다.

## Nginx와 TLS

- 80 포트는 ACME challenge를 제외하고 HTTPS로 redirect한다.
- 443 포트는 TLS 1.2/1.3을 사용한다.
- `/` 전체를 backend:8000으로 프록시한다.
- `/docs`, `/redoc`, `/admin/*`에 Nginx 자체 인증은 없다. `/admin/*`는 애플리케이션의 `X-Admin-Key` 인증을 거치지만 `/docs`와 `/redoc`은 별도 보호가 없다.

## 현재 CI 한계

배포 워크플로에는 Ruff, 자동 테스트, TypeScript, ESLint, 프론트엔드 build, 배포 후 health check가 품질 게이트로 연결돼 있지 않다. Docker 이미지가 빌드되면 운영 배포로 진행한다.

배포 파이프라인 변경 시 권장 순서는 다음과 같다.

1. 백엔드 Ruff와 테스트
2. 프론트엔드 lint, typecheck, build
3. 이미지 빌드
4. staging 또는 새 컨테이너 health 확인
5. 트래픽 전환
6. 실패 시 이전 SHA 이미지로 rollback
