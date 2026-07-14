# ADR-005: Docker 배포 환경에서의 SQLite WAL 모드 영속성 전략

## Status
Accepted

## Date
2026-07-14

## Context
Trading Server는 고성능 동시성 처리를 위해 로컬 데이터베이스인 SQLite와 WAL(Write-Ahead Logging) 저널 모드를 사용한다.
GitHub Actions를 통해 OCI 서버에 Docker 컨테이너 형태로 배포(CD)를 자동화하는 과정에서, DB 파일(`trading.db`)을 어떻게 호스트 서버에 마운트하여 영구 보존(Persistence)할 것인가에 대한 아키텍처 결정이 필요했다.
특히 로컬 환경과 동일하게 배포 서버의 프로젝트 루트 폴더에 `trading.db`를 직접 위치시키는 방안이 제안되었다.

## Decision
서버의 프로젝트 루트 폴더나 단일 파일을 마운트하는 방식을 모두 기각하고, **별도의 전용 폴더(`./data:/app/data`)를 마운트한 뒤 환경 변수(`SQLITE_DB_PATH`)를 통해 DB 경로를 주입하는 방식**을 채택했다.

## Alternatives Considered

### 1. 단일 파일 마운트 (`- ./trading.db:/app/trading.db`)
- **장점**: 루트 폴더에 직관적으로 파일 1개가 위치함.
- **단점 (치명적)**: SQLite WAL 모드는 런타임에 `.db-wal`, `.db-shm` 임시 파일을 수시로 생성함. 단일 파일로 마운트하면 이 임시 파일들이 도커의 볼륨 바인딩에 포함되지 않고 컨테이너 내부(휘발성 영역)에 격리되어 생성됨. 컨테이너 종료나 재시작 시 데이터가 메인 DB에 병합(Checkpoint)되지 못하고 증발하여 **DB Corrupted(데이터베이스 손상) 에러**를 유발함.
- **결과**: **기각 (안정성 문제)**

### 2. 프로젝트 루트 전체 마운트 (`- ./:/app`)
- **장점**: WAL 보조 파일들도 함께 호스트에 마운트되며, 사용자가 원하는 직관적인 디렉토리 구조를 달성할 수 있음.
- **단점 (치명적)**: 현재 OCI 서버의 배포 경로(`~/Trading`)에는 GitHub Actions가 전송한 인프라 파일(`docker-compose.yml`, `.env`, `.nginx/` 등)만 존재하며 파이썬 소스코드가 없음 (소스코드는 GitHub Container Registry 이미지 내부에 패키징됨).
따라서 텅 빈 호스트의 루트 폴더를 컨테이너 내부의 `/app`에 덮어씌워(Mount) 버리면, 도커 이미지 내부의 소스코드와 `.venv`가 모두 마운트에 가려져 서버가 실행 불가능한 상태가 됨.
- **결과**: **기각 (도커 이미지 구조 파괴)**

## Consequences
- 데이터베이스 전용의 독립적인 폴더(`./data`)를 사용함으로써 컨테이너 내부의 소스코드(Image Layer)와 호스트의 인프라 설정 파일 간의 불필요한 결합을 원천 차단했다.
- 백엔드 애플리케이션(`app/core/database.py`)에서 `SQLITE_DB_PATH` 환경 변수를 우선적으로 읽도록 설계되어 있었기에, 코드 수정 없이 Docker Compose의 환경 변수 주입(`SQLITE_DB_PATH=/app/data/trading.db`)만으로 우아하게 영속성 문제를 해결할 수 있었다.
- 추후 백업 전략 수립 시, `data/` 폴더만 통째로 압축하여 주기적으로 덤프하면 되므로 운영 편의성이 극대화되었다.
