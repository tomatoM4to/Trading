# 배포와 인프라

## 구성

| 컴포넌트 | 역할 |
|---|---|
| backend | FastAPI와 인메모리 SQLite |
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

필요 Secrets:

- 서버: `OCI_HOST`, `OCI_USERNAME`, `OCI_SSH_KEY`, `DOMAIN`
- 레지스트리: `CR_PAT`
- KIS: `KIS_MY_APP`, `KIS_MY_SEC`, `KIS_MY_HTSID`, `KIS_MY_ACCT_STOCK`, `KIS_MY_PROD`

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
- `/docs`, `/redoc`, `/admin/*`도 별도 인증 없이 외부에서 도달 가능하다.

## 현재 CI 한계

배포 워크플로에는 Ruff, 자동 테스트, TypeScript, ESLint, 프론트엔드 build, 배포 후 health check가 품질 게이트로 연결돼 있지 않다. Docker 이미지가 빌드되면 운영 배포로 진행한다.

배포 파이프라인 변경 시 권장 순서는 다음과 같다.

1. 백엔드 Ruff와 테스트
2. 프론트엔드 lint, typecheck, build
3. 이미지 빌드
4. staging 또는 새 컨테이너 health 확인
5. 트래픽 전환
6. 실패 시 이전 SHA 이미지로 rollback
