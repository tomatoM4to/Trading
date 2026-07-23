# ADR-008: DEBUG와 SCHED 환경 변수의 분리 및 로깅 레벨 조정

## Status
Accepted

## Date
2026-07-23

## Context
기존 시스템에서는 `.env` 파일의 `DEBUG` 환경 변수가 두 가지 역할을 동시에 수행하도록 강하게 결합(Coupling)되어 있었습니다.
1. KIS OpenAPI 인증 토큰의 캐시 사용 여부 결정 (`DEBUG=True` 시 캐시 사용, `False` 시 강제 재발급)
2. 백그라운드 시스템 스케줄러(`SystemScheduler`) 및 부트스트랩 파이프라인의 구동 여부 결정

이로 인해 "운영 토큰 갱신 로직을 테스트하고 싶지만 스케줄러는 끄고 싶을 때"와 같은 세밀한 개발 및 디버깅 제어가 불가능했습니다. 또한, 성능 최적화를 명목으로 `app/core/logging.py`의 기본 루트 로그 레벨이 `WARNING`으로 설정되어 있어, 앱 부팅 시 출력되어야 할 중요한 상태 로그(`logger.info`, `logger.sched`)가 개발자의 콘솔에 전혀 노출되지 않는 문제가 있었습니다.

## Decision
1. **환경 변수 역할의 명확한 분리 (Decoupling)**
   - `DEBUG`: 오직 인증 토큰의 발급 방식(캐시 재사용 vs 강제 발급)만을 제어합니다.
   - `SCHED`: 오직 스케줄러 및 부트스트랩 파이프라인의 백그라운드 가동 여부만을 제어합니다.
   
2. **초기 인증 프로세스 중앙화 및 Non-blocking 처리**
   - 부팅 시의 KIS 토큰 발급 로직을 `app/main.py`의 `lifespan` 내로 완전히 끌어올렸습니다. 
   - HTTP 통신 시 발생하는 I/O 블로킹이 FastAPI 메인 루프를 지연시키지 않도록 `await asyncio.to_thread(auth, force=...)` 패턴을 적용했습니다.
   - 이에 따라 `SystemScheduler.start()` 내부에 중복으로 존재하던 초기 `auth()` 호출 로직(Double Auth 발생 원인)을 제거했습니다.

3. **기본 로깅 레벨 환경변수화 및 기본값 하향 조정**
   - 기존의 하드코딩된 `WARNING(30)` 위주의 로깅 설정 대신 `LOG_LEVEL` 환경 변수를 도입하여 동적으로 제어할 수 있도록 개선했습니다.
   - 로컬 개발 및 디버깅 편의성을 위해 기본값(Default)을 `INFO(20)`로 하향 조정하여 `logger.sched`와 같은 주요 상태 로그가 기본적으로 노출되도록 하되, 운영 환경에서는 언제든 `.env`에 `LOG_LEVEL=WARNING`을 선언하여 디스크 I/O 최적화를 이룰 수 있도록 조치했습니다. 

## Consequences
- 개발자는 `.env`를 통해 가벼운 단건 API 테스트 환경(`SCHED=False`)부터 완전한 실전 배포 환경(`DEBUG=False, SCHED=True`)까지 조합하여 사용할 수 있게 되었습니다.
- 시스템 기동 시 터미널을 통해 현재 어떤 모드(DEBUG, SCHED)로 작동 중인지 직관적으로 파악할 수 있게 되어 디버깅 편의성이 대폭 향상되었습니다.
- 부팅 시 초기화 로직의 순서가 명확해져(토큰 발급 완료 ➡️ 스케줄러 가동) Race Condition 및 API 과호출 에러 가능성이 원천 차단되었습니다.
