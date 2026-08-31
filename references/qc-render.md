# Render and Visual QC

렌더는 결과를 만드는 단계가 아니라 검증을 위한 증거를 만드는 단계다. 반드시 첫 프레임, 변화 직전, 전환 중간, 변화 종료 직후, 마지막 프레임을 `ae_render_frame`으로 확인한다. 필요하면 Alpha 채널 보기와 최종 컬러 보기 모두 캡처한다.

## QC gate

| Gate | 통과 기준 |
|---|---|
| Structure | comp 이름·fps·해상도·길이가 brief와 일치 |
| Mapping | 모든 소스가 의도한 레이어에 연결되고 offline 없음 |
| Timing | 시작 hold·transition·종료 hold가 정확함 |
| Matte | 누출·halo·떨림·검은 테두리 없음 |
| Color | 샷 간 노출·WB·룩이 일관되고 clipping 없음 |
| Render | 실제 출력 파일이 preview와 일치 |
| Save | 새 aep와 review 영상이 보존됨 |

최종 보고에는 사용한 comp, output path, codec, 색상 공간, 변경 목록, 미해결 사항을 기록한다. 프레임 캡처가 실패하면 렌더 완료로 간주하지 않는다.
