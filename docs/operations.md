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

### GC

`POST /admin/action/gc`는 즉시 지능형 GC를 실행한다. 데이터 삭제와 디스크 동기화를 포함하므로 장중 호출을 피한다.

### 통합 검증

- `GET /admin/test/daily_scheduler`
- `GET /admin/test/minute_scheduler`

테스트 DB를 만들고 표본 종목에 대해 수집 파이프라인을 실행한다. 독립 자동 테스트 대체물이 아니며 KIS 호출과 로컬 파일 I/O를 발생시킨다.

## 운영 보안 경고

`/admin/*`은 애플리케이션 API 키로 보호된다. `/docs`, `/redoc`은 인증이 없으므로 운영 서버를 공용 인터넷에 노출한다면 다음 중 하나 이상을 추가로 적용한다.

- Nginx IP allowlist
- 관리자 경로에 대한 Nginx 추가 인증
- VPN 또는 private network
- 운영 빌드에서 test router 제외
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

표준 `unittest` 기반 회귀 테스트는 다음 명령으로 실행한다.

```powershell
uv run python -m unittest discover -s tests -v
```

다음 영역은 추가 테스트 대상으로 본다.

- 스크리너 입력 검증과 AND/OR 의미론
- 일봉/분봉 테이블 선택
- SystemState 중첩 acquire/release
- ContextVar DB 격리
- STRICT 날짜·시간 변환
- KIS 큐 우선순위와 호출 간격
- 차트 캔들·MA 집계

## 장애 점검 순서

1. `/health` 확인
2. 503이면 `detail`과 백그라운드 작업 로그 확인
3. 컨테이너와 Nginx 로그 확인
4. KIS 인증 오류와 토큰 캐시 확인
5. `/admin/live`로 최신 적재 시각 확인
6. 디스크의 `data/trading.db`와 volume mount 확인
7. 재시작 전에 마지막 메모리→디스크 동기화 성공 로그 확인

## 알려진 운영 위험

- API 문서가 인증 없이 노출된다.
- 배포 전에 자동 품질 게이트가 없다.
- Compose 배포가 컨테이너를 먼저 내리므로 중단 시간이 있다.
- AST AND/OR 의미론과 수집 파이프라인 전반의 자동 회귀 테스트가 부족하다.
