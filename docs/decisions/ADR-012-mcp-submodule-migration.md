# ADR-012: Git Submodule 및 Sparse-Checkout을 활용한 외부 MCP 통합

## Status
Accepted

## Date
2026-07-29

## Context
본 프로젝트는 KIS OpenAPI 연동을 위해 공식 레포지토리(`koreainvestment/open-trading-api`)에서 제공하는 `kis-code-assistant-mcp`를 사용하고 있습니다. 
초기에는 해당 코드를 프로젝트 내부에 직접 복사/붙여넣기(하드코딩)하여 사용했으나 다음과 같은 문제점이 발생했습니다:
- 원본 레포지토리의 지속적인 업데이트(버그 픽스, 기능 추가)를 쉽게 추적하고 반영(Pull)하기 어려움.
- 본 프로젝트의 Git 커밋 로그 및 파일 트리가 우리가 직접 관리하지 않는 거대한 외부 코드로 인해 오염됨.

## Decision
- 외부 MCP 서버 및 라이브러리 코드는 프로젝트에 직접 복사하지 않고 **Git Submodule**을 사용하여 공식 원본 레포지토리를 연결합니다.
- 단, 무거운 전체 레포지토리 파일이 워크스페이스를 어지럽히는 것을 막기 위해 **Git Sparse-Checkout** 기능을 결합합니다. 이를 통해 필요한 특정 하위 폴더(예: `MCP/KIS Code Assistant MCP`)만 로컬 파일 시스템에 노출되도록 구성합니다.

## Alternatives Considered

### 단순 복사/붙여넣기 (기존 방식)
- Pros: 초기 세팅이 매우 빠르고 단순함.
- Cons: 업스트림 변경 사항을 동기화하기 어렵고 지속적인 수동 관리가 필요함.
- Rejected: 장기적인 유지보수성이 떨어져 기각.

### 자체 Fork 생성 및 커스터마이징
- Pros: 필요에 따라 코드를 마음대로 수정할 수 있음.
- Cons: 원본 업데이트를 병합(Merge)할 때마다 충돌(Conflict) 해결 리소스가 발생함. (현재 커스텀 수정 니즈 없음)
- Rejected: 수정 없이 원본 그대로 사용하는 것이 가장 효율적이므로 기각.

## Consequences
- `.gitmodules` 파일을 통해 버전(커밋 Hash)이 추적되므로, 부모 프로젝트의 Git 로그가 깔끔하게 유지됩니다.
- Antigravity IDE 등의 설정 파일(`.agents/mcp_config.json`) 내 MCP 구동 경로는 새 서브모듈 경로(`open-trading-api/MCP/KIS Code Assistant MCP`)를 바라보도록 유지해야 합니다.
- 타 개발자가 레포지토리를 새로 Clone할 경우, 일반적인 Clone 외에 서브모듈 초기화 및 Sparse-Checkout 세팅이 추가로 필요해집니다.
