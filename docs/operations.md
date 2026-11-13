# 운영과 검증

## 상태 확인

### 프로세스 상태

`GET /health`는 시스템 가드를 우회하며 항상 애플리케이션 프로세스의 응답 가능 여부를 확인한다.

```json
{
  "status": "ok",
  "timestamp": "2026-08-21T12:34:56",
  "app": "Trading Server"
}
```

이 응답은 DB 적재 완료나 KIS 인증 유효성을 보장하지 않는다.

### 데이터 적재 상태

- 전체: `GET /admin/live/global-status?data_type=daily|minute`
- 종목: `GET /admin/live/ticker-status/{ticker}?data_type=daily|minute`

모든 `/admin/*` 요청에는 `X-Admin-Key: <ADMIN_API_KEY>` 헤더가 필요하다.

최신 날짜·시간과 보유 행 수를 확인해 수집 지연을 판단한다.

## 시스템 가드 해석

503 응답의 `detail`에는 현재 차단 이유가 들어간다. 부트스트랩, 종목 마스터 동기화, 일봉 업데이트, GC 중에는 정상적인 보호 동작일 수 있다. `/health`까지 실패할 때만 프로세스 또는 프록시 장애를 우선 의심한다.

## 수동 작업

### 콜드 스타트 배포

`trading.db`를 비우는 배포는 재구축 가능성을 실제로 검증하는 운영 방식이다. 장중 분봉 수집과 16시 일봉 갱신을 피하기 위해 18시 이후에 진행한다.

1. 백엔드 로그에서 당일 수집 작업 종료를 확인한다.
2. `docker compose down`으로 SQLite 연결을 정상 종료한다.
3. 필요하면 `trading.db`를 삭제하는 대신 `trading.db.pre-beta`처럼 이름을 바꿔 롤백 사본을 남긴다.
4. 새 이미지를 시작하고 마스터·일봉 수집, MA 재구축, 분봉 수집 로그를 순서대로 확인한다.
5. `/health`, `/admin/live`, 스크리너 결과와 컨테이너 메모리를 확인한다.

롤백 사본은 데이터 보존 의무가 아니라 KIS 장애·호출 제한·신규 코드 오류가 발생했을 때 복구 시간을 줄이는 선택 사항이다. 콜드 스타트 중 `/health`는 응답할 수 있어도 데이터 적재와 MA 준비가 완료됐다는 뜻은 아니다. 200개 캔들이 없는 종목의 `ma200`은 `NULL`이며 해당 MA 스크리너 결과에서만 제외된다.

### GC

`POST /admin/action/gc`는 즉시 지능형 GC를 실행한다. 데이터 삭제와 WAL 체크포인트를 포함하므로 장중 호출을 피한다.

### 통합 검증

`/admin/test/*`는 MA DB 격리가 되지 않는 레거시 기능이라 삭제했다. [격리 pytest 및 Docker 검증](testing.md)을 사용한다. `/admin/live/*` 상태 조회와 `/admin/action/gc`는 유지한다.

## 운영 보안 경고

`/admin/*`은 애플리케이션 API 키로 보호된다. `/docs`, `/redoc`은 인증이 없으므로 운영 서버를 공용 인터넷에 노출한다면 다음 중 하나 이상을 추가로 적용한다.

- Nginx IP allowlist
- 관리자 경로에 대한 Nginx 추가 인증
- VPN 또는 private network
- API 문서 비활성화 또는 인증

보호가 구현되기 전에는 관리자 경로를 외부 사용자용 API로 취급하지 않는다.

## 변경 검증

### 백엔드

```powershell
uv run ruff check .
uv run ruff format --check .
```

### 프론트엔드

```powershell
cd web
npm run lint
npx tsc --noEmit
npm run build
```

pytest 기반 백엔드 정합성 하네스는 다음 명령으로 실행한다.

```powershell
uv run --locked pytest
```

Stage별 명령·실행 결과·실제 API 선택 검증 및 미검증 범위는 [testing.md](testing.md)를 따른다. 현재 Windows 기본 실행은 미해결 T12의 4개 사례 때문에 종료 코드 1이다. [test-defects.md](test-defects.md)의 수정 이력을 확인하고, 남은 실패를 skip하거나 기대값을 완화해 숨기지 않는다.

## 장애 점검 순서

1. `/health` 확인
2. 503이면 `detail`과 백그라운드 작업 로그 확인
3. 컨테이너와 Nginx 로그 확인
4. KIS 인증 오류와 토큰 캐시 확인
5. `/admin/live`로 최신 적재 시각 확인
6. 디스크의 `data/trading.db`와 volume mount 확인
7. 재시작 전에 마지막 WAL 체크포인트 성공 로그 확인

## 알려진 운영 위험

- API 문서가 인증 없이 노출된다.
- 배포 전에 자동 품질 게이트가 없다.
- Compose 배포가 컨테이너를 먼저 내리므로 중단 시간이 있다.
- Queue·수집·최적화·복구의 요청된 결함은 오프라인 하네스로 수정 검증했다. Windows MA ATTACH(T12), 실제 KIS·Linux·1GB 장시간 환경 검증은 남아 있다.
