# After Effects Codex Agent

After Effects를 실제로 읽고 수정하는 After Effects MCP와 Codex의 판단·검수 규칙을 결합하기 위한 독립 문서 저장소다. 이 저장소는 실행 서버 자체의 소스가 아니며, `src/`, `jsx/`, `tests/`, `package.json`을 복제하지 않는다.

## 구조

| 경로 | 역할 |
|---|---|
| `AGENTS.md` | Codex 진입점과 reference 선택 규칙 |
| `SKILL.md` | 조사→계획→수정→시각 검수→저장 workflow |
| `references/` | 합성, 매트, 색상, 애니메이션, 렌더, 문제 해결 기준 |
| `templates/task-brief.md` | 실제 작업 지시 템플릿 |
| `THIRD_PARTY_NOTICES.md` | 외부 프로젝트·상표·문서 고지 |

## 사용 순서

Codex 프로젝트 지침 위치에 이 폴더를 배치한 뒤 `AGENTS.md`와 `SKILL.md`를 읽는다. 작업마다 `templates/task-brief.md`를 복사해 대상 컴포지션과 변경 범위를 채운다. AE에 연결된 MCP가 제공하는 operation은 `ae_catalog`로 확인하며, 이 저장소는 특정 버전의 operation 목록을 고정하지 않는다.

After Effects MCP 연결, Node.js, AE 버전, 네트워크·스크립트 권한은 실제 설치 환경의 공식 문서를 기준으로 확인한다. 이 저장소의 문서는 실행 서버를 대신하지 않는다.

## 안전 원칙

원본 `.aep`를 덮어쓰지 않고 새 버전 또는 새 프로젝트로 저장한다. 모든 mutation 전후에 AE 상태를 조회하고, 첫 프레임·중간 프레임·마지막 프레임을 렌더링해 확인한다. 요청하지 않은 소스 교체, 색감 변경, 타이밍 변경, 레이어 순서 변경은 하지 않는다.

## 라이선스

문서와 템플릿의 라이선스 범위는 `THIRD_PARTY_NOTICES.md`를 확인한다. Adobe, After Effects, Codex 및 관련 상표는 각 권리자에게 귀속된다.
