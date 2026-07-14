# ADR-006: 민감한 환경설정 파일(YAML, ENV)의 동적 생성 전략

## Status
Accepted

## Date
2026-07-14

## Context
Trading Server 프로젝트는 KIS OpenAPI 연동을 위해 `kis_devlp.yaml` 파일과 `.env` 파일을 애플리케이션 초기화에 강하게 의존하고 있다 (`app/core/kis_auth.py` 등).
보안 원칙에 따라 이 두 파일은 `.gitignore`에 등록되어 GitHub 레포지토리에 푸시되지 않는다.

GitHub Actions 기반의 Docker 빌드/배포를 자동화하면서 다음과 같은 치명적 이슈가 발생했다:
- 도커 이미지(`Dockerfile`)는 GitHub 레포지토리의 소스코드를 기반으로 빌드되므로, 무시된 `kis_devlp.yaml`과 `.env`는 도커 이미지 내부에 포함되지 않는다.
- 결과적으로, 배포 후 컨테이너가 실행되면 `kis_auth.py`가 설정 파일을 찾지 못해 즉시 **서버 Crash**가 발생하는 구조적 결함이 있었다.

## Decision
소스코드에 설정 파일을 하드코딩하거나 억지로 도커 이미지에 포함시키는 대신, **GitHub Actions 파이프라인이 SSH를 통해 서버에 접속하여 설정 파일을 동적으로 생성(Generate)하고 도커 볼륨으로 마운트(Bind Mount)하는 방식**을 채택했다.

## Alternatives Considered

### 1. 도커 이미지 내부에 Secret 주입하여 빌드
- **장점**: 컨테이너 내부에 파일이 내장되므로 볼륨 마운트가 필요 없음.
- **단점**: 빌드된 이미지 내부에 KIS App Key 같은 민감 정보가 영구적으로 남아, GHCR과 같은 레지스트리 보안에 크게 의존하게 됨. 이미지가 유출되면 계좌 정보 전체가 털림.
- **결과**: 기각.

### 2. AWS Parameter Store 혹은 HashiCorp Vault 사용
- **장점**: 가장 안전하고 엔터프라이즈급의 동적 시크릿 관리가 가능함.
- **단점**: 아키텍처가 너무 무거워지고, Oracle Cloud Free Tier의 제약(1 OCPU/1GB) 환경에서 오버엔지니어링임.
- **결과**: 기각.

## Consequences
- 설정 파일(`kis_devlp.yaml`, `.env`) 생성 로직을 `setup-server.yml`과 `deploy.yml`에 인라인 Bash 스크립트(`cat <<EOF`) 형태로 주입했다.
- 이로 인해 개발자는 로컬 코드를 전혀 수정할 필요 없이 **GitHub Secrets 탭에서 키값을 갱신하기만 하면**, 다음 배포 시 자동으로 서버의 YAML 파일이 최신화된다.
- 결과적으로 **"소스코드의 완벽한 보안(Secret-Free Image)"**과 **"배포 파이프라인의 유연성"**이라는 두 마리 토끼를 잡았다.
- `docker-compose.yml`에서는 `- ./kis_devlp.yaml:/app/kis_devlp.yaml:ro` 형태로 안전하게 컨테이너 내부로 설정 파일을 주입하게 된다.
