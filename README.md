# After Effects Codex Agent

After Effects를 실제로 읽고 수정하는 After Effects MCP와 Codex의 판단·검수 규칙을 결합하기 위한 독립 문서 저장소다. 이 저장소는 실행 서버 자체의 소스가 아니며, `src/`, `jsx/`, `tests/`, `package.json`을 복제하지 않는다.

## 구조

| 경로 | 역할 |
|---|---|
| `AGENTS.md` | Codex 진입점과 reference 선택 규칙 |
| `SKILL.md` | 조사→계획→수정→시각 검수→저장 workflow |
| `references/` | 합성, 매트, 색상, 애니메이션, 렌더, 문제 해결 기준 |
| `templates/task-brief.md` | 실제 작업 지시 템플릿 |
| `scripts/ae-swap-footage-suffix.jsx` | 프로젝트에 쓰인 영상만 `<원본명>_skin` 같은 접미사 버전으로 교체 → 기존 렌더 큐(영상·첫/아웃 프레임) 같은 경로로 재출력 → 프로젝트에 없는 소스는 휴지통 |
| `THIRD_PARTY_NOTICES.md` | 외부 프로젝트·상표·문서 고지 |

## 사용 순서

Codex 프로젝트 지침 위치에 이 폴더를 배치한 뒤 `AGENTS.md`와 `SKILL.md`를 읽는다. 작업마다 `templates/task-brief.md`를 복사해 대상 컴포지션과 변경 범위를 채운다. AE에 연결된 MCP가 제공하는 operation은 `ae_catalog`로 확인하며, 이 저장소는 특정 버전의 operation 목록을 고정하지 않는다.

After Effects MCP 연결, Node.js, AE 버전, 네트워크·스크립트 권한은 실제 설치 환경의 공식 문서를 기준으로 확인한다. 이 저장소의 문서는 실행 서버를 대신하지 않는다.

## 소스 일괄 교체 스크립트

MCP 없이 AE에서 직접 돌리는 ExtendScript다. `파일 > 스크립트 > 스크립트 파일 실행…`으로 `scripts/ae-swap-footage-suffix.jsx`를 연다(환경설정 > 스크립팅 및 표현식 > "스크립트가 파일을 쓰고 네트워크에 액세스하도록 허용" 필요).

1. 접미사(기본 `_skin`)를 정한다. 원본 `A.mov`의 짝은 `A_skin.mov`다.
2. 교체 영상을 이미 받아 둔 폴더를 고르거나, Synology 폴더 공유 링크를 넣는다(링크면 프로젝트에 쓰인 것만 받는다).
3. 확인 창에서 교체 목록·짝 없음·재렌더 항목·휴지통 목록을 보고 실행한다.

원본 `.aep`는 그대로 두고 `<이름>_skin.aep`로 새로 저장한다. 효과·LUT·키프레임·렌더 설정은 바꾸지 않고, 바뀐 footage 해석은 원래 값으로 되돌린다. 기존 출력은 `*_preskin.*`으로 백업한 뒤 같은 경로에 다시 렌더하고, 결과·길이/fps 차이·휴지통 내역을 `<이름>_skin_swap_report.txt`에 남긴다. 파일명이 정확히 같지 않은 후보는 확인 창에서 직접 켜야만 교체하고, 받는 중인 파일(`.crdownload`·`.part`)은 교체·휴지통 모두에서 뺀다. 정확히 맞은 파일이 하나도 없으면 휴지통 옵션은 꺼진다.

## 안전 원칙

원본 `.aep`를 덮어쓰지 않고 새 버전 또는 새 프로젝트로 저장한다. 모든 mutation 전후에 AE 상태를 조회하고, 첫 프레임·중간 프레임·마지막 프레임을 렌더링해 확인한다. 요청하지 않은 소스 교체, 색감 변경, 타이밍 변경, 레이어 순서 변경은 하지 않는다.

## 라이선스

문서와 템플릿의 라이선스 범위는 `THIRD_PARTY_NOTICES.md`를 확인한다. Adobe, After Effects, Codex 및 관련 상표는 각 권리자에게 귀속된다.
