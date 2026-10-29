# Trading Dashboard

Next.js 기반 스크리너·차트 UI다. 프로젝트 전체 실행 절차는 [루트 README](../README.md), 컴포넌트 책임과 API 흐름은 [프론트엔드 문서](../docs/frontend.md)에 있다.

## Run

이 디렉터리에서 실행한다. 백엔드는 별도 터미널에서 준비해야 한다.

```powershell
npm ci
$env:NEXT_PUBLIC_API_URL = "http://localhost:8000"
npm run dev
```

http://localhost:3000 에서 연다. `NEXT_PUBLIC_API_URL`은 클라이언트에 노출되는 API 주소다. KIS 자격 증명이나 관리자 키를 넣지 않는다.

## Verify

```powershell
npm run lint
npx tsc --noEmit
npm run build
```

필터·SSE·차트 변경은 [검증 기준](../docs/frontend.md#검증)에 따라 브라우저에서도 확인한다. 작업 전 [AGENTS.md](AGENTS.md)를 읽는다.
