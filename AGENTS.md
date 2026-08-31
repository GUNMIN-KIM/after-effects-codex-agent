# After Effects Codex Agent

이 저장소는 **Windows/macOS에서 After Effects MCP와 함께 사용하는 Codex 작업 지침**이다. 사용자의 자연어 요청을 실제 AE 편집 작업으로 바꿀 때는 반드시 `SKILL.md`를 먼저 읽고, 작업 성격에 맞는 reference 문서를 추가로 읽는다.

## 실행 규칙

작업은 항상 다음 순서를 따른다.

`UNDERSTAND → INSPECT → PLAN → PROTECT → EXECUTE → RE-INSPECT → RENDER FRAME → VISUAL QA → REPAIR → FINAL QC → SAVE`

합성·레이어·렌더·색상·매트·키프레임을 추측하지 않는다. AE의 현재 상태를 먼저 조회하고, 소스·컴포지션·레이어 ID를 확인한 뒤 최소 변경으로 실행한다. 작업 전후에 사용자가 요청한 변경 항목과 변경하지 않은 항목을 분리해 기록한다.

## reference 선택표

| 작업 유형 | 반드시 읽을 문서 |
|---|---|
| 모든 AE 작업 | `SKILL.md`, `references/operations-and-safety.md` |
| 합성·VFX·광원·질감 | `references/compositing.md` |
| Alpha/Luma/Track Matte/Roto | `references/matte-roto.md` |
| DI·컬러·노출·화이트밸런스·Glow | `references/color.md` |
| 애니메이션·전환·키프레임 | `references/animation.md` |
| 프레임 캡처·렌더·시각 검수 | `references/qc-render.md` |
| 오류·오프라인·타이밍·품질 회귀 | `references/troubleshooting.md` |

실제 MCP operation 이름이나 인자 형식은 문서에 하드코딩하지 않는다. 연결된 MCP가 제공하는 `ae_catalog`를 런타임에 조회하고, 현재 환경에서 확인된 operation만 사용한다.

## 보호 규칙

기존 `.aep`는 명시적 허가 없이는 덮어쓰지 않는다. 기본 동작은 새 프로젝트 또는 새 버전 저장이다. 파일 삭제, 대량 변경, 렌더 큐 제출, 외부 파일 생성은 실행 전에 범위와 경로를 명시한다. 오류가 발생하면 추가 mutation을 멈추고 상태를 다시 읽은 뒤 원인을 분리한다.
