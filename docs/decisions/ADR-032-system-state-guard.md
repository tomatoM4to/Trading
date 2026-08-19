# ADR-032: 시스템 상태 객체 기반 글로벌 API 차단기 (System State Guard) 도입

## Status
Accepted

## Date
2026-08-12

## Context
1 OCPU, 1GB RAM 환경의 매우 제한적인 리소스를 가진 서버에서, 지능형 GC, 콜드스타트(전체 데이터 적재), 인메모리 DB 동기화(디스크 백업) 등 무거운 백그라운드 작업이 실행될 때 사용자의 API 요청이 인입되면 다음과 같은 치명적인 문제가 발생할 수 있습니다.
- SQLite 파일 잠금(Lock) 에러 (WinError 32 등)
- 메모리 사용량 급증으로 인한 서버 다운(OOM Crash)
- 불완전한 상태의 데이터(예: GC 도중)가 API로 서빙되어 발생하는 정합성(Integrity) 파괴

이러한 순간에는 데이터를 주는 것보다 즉시 요청을 튕겨내어 서버의 생존과 무결성을 보장하는 것이 최우선 목표가 되어야 합니다.

## Decision
FastAPI의 전역 의존성 주입(Global Dependency)과 파이썬의 싱글톤 컨텍스트 매니저를 결합한 **System State Guard** 패턴을 도입합니다.

1. **상태 관리 (`SystemState`)**: 
   - 스레드 안전(Thread-safe)한 전역 상태 객체를 만들어, 무거운 작업 진입 시 `with system_state.acquire("GC 중"):` 처럼 락을 잡습니다.
   - 내부적으로 `_acquire_count`를 유지하여 중첩되거나 병렬로 실행되는 백그라운드 작업들에 대해서도 완벽히 상태를 잠그고, 모든 작업이 종료된 후에만 락을 해제합니다.
2. **글로벌 API 방어벽 (`system_state_guard`)**: 
   - `FastAPI(dependencies=[Depends(system_state_guard)])`를 통해 앱 전체에 의존성을 주입합니다.
   - 락이 걸린 상태에서 API 호출 시, 즉시 `HTTP 503 (Service Unavailable)`과 `{"detail": "GC 중"}` 사유를 반환하여 큐잉이나 대기 없이 빠르게 거절(Fail-fast)합니다.
3. **로드밸런서 예외 처리**: 
   - 상태 모니터링을 위한 `/health` 라우터만큼은 의존성 내부에서 `request.url.path == "/health"` 조건으로 강제 패스(bypass)시켜, 서버가 비정상 종료된 것으로 오인되지 않게 보호합니다.

## Alternatives Considered

### 클라이언트 자동 재시도 큐(Queue) 및 차단 권한 분리
- **Pros**: 유저가 에러를 덜 보고 대기(Loading) 상태를 경험하게 됨.
- **Cons**: 큐에 쌓인 요청 자체가 1GB 서버의 메모리를 압박할 수 있으며, 구조가 매우 복잡해짐.
- **Rejected**: 즉시 거절하고 클라이언트가 알아서 나중에 재시도하게 만드는 Fail-fast가 시스템 생존 확률을 극대화합니다.

## Consequences
- 데이터 적재나 싱크 작업 중 쏟아지는 트래픽으로부터 DB와 서버가 완벽히 보호됩니다.
- 데드락 방지: 예외(Exception)가 발생해 백그라운드 작업이 비정상 종료되어도, `contextmanager`의 `finally` 덕분에 무조건 상태가 롤백(Available)되므로 서버가 영구적으로 마비되지 않습니다.
- 프론트엔드는 HTTP 503 코드와 명확한 사유를 전달받아 "서버 점검 중" 팝업 등 유려한 에러 핸들링이 가능해집니다.
