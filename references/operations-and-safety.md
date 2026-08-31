# Operations and Safety

After Effects MCP는 AE와 통신하는 실행 계층이다. operation 이름과 인자는 실행 시 `ae_catalog`에서 발견하고 현재 연결된 서버가 제공하는 것만 사용한다. `ae_context`는 현재 선택·활성 컴포지션의 문맥, `ae_project_info`는 프로젝트 상태, `ae_comp_info`는 컴포지션 상태, `ae_layer_info`는 레이어 속성, `ae_do`는 mutation, `ae_render_frame`은 시각 검수에 사용한다.

## 안전 gate

| Gate | 통과 조건 |
|---|---|
| Read | 프로젝트·컴프·레이어·소스의 현재 상태를 읽음 |
| Plan | 변경 대상과 보존 대상이 분리됨 |
| Protect | 새 프로젝트/버전 저장 경로가 확정됨 |
| Mutate | stable ID와 검증된 operation만 사용 |
| Verify | 변경 직후 상태 재조회와 프레임 렌더 완료 |
| Save | aep·렌더·변경 로그가 별도 저장됨 |

작업 중 timeout, unknown operation, ambiguous layer, offline footage, expression error가 발생하면 mutation을 계속하지 않는다. 다시 읽고 원인을 분리한다. arbitrary ExtendScript는 기본 수단으로 사용하지 않으며, 필요할 때도 사용자 요청 범위·파일 경로·되돌리기 방법을 먼저 기록한다. 대량 변경은 작은 batch로 나누고 각 batch 뒤에 re-inspect한다.
