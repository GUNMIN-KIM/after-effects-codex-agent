# Troubleshooting

문제 해결은 `소스 → 시간축 → 매트 → 색상 → 효과 → 출력` 순서로 진행한다. 한 번에 여러 변수를 바꾸지 말고 증상을 재현하는 최소 프레임을 고정한다.

| 증상 | 진단 순서 |
|---|---|
| MCP timeout | 연결 상태와 catalog 재조회 후 작은 read operation부터 재시도 |
| unknown operation | operation을 추측하지 말고 ae_catalog에서 현재 이름 확인 |
| offline footage | Windows 경로·파일 존재·footage 해석을 확인 |
| 검은 화면 | source 연결, alpha interpretation, matte mode 확인 |
| halo/fringe | Straight/Premultiplied, choke, feather, color spill 확인 |
| timing 오류 | comp fps와 in/out, keyframe time, work area 확인 |
| 렌더 불일치 | preview가 아닌 실제 output module과 프레임 확인 |
| 품질 회귀 | 이전 통과 프레임과 동일 조건으로 재렌더 |
