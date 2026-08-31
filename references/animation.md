# Animation and Keyframes

모든 동작은 fps와 시간코드로 지시한다. 위치·스케일·불투명도·매트 진행률·라벨·글로우를 하나의 transition controller에 연결하면 버전 간 일관성이 좋아진다. 전환 전후 hold 구간과 실제 transition duration을 분리한다.

예: 4초, 24fps라면 ORIGINAL 0–1.5초 hold, 1.5–2.5초 transition, FINAL VFX 2.5–4초 hold다. 키프레임을 생성한 뒤 `U`로 속성과 시간을 검수한다. 빠른 전환은 duration을 줄이는 것이지 전체 타임라인을 임의로 당기는 것이 아니다.

| 동작 | 기본 원칙 |
|---|---|
| Linear | 일정한 속도가 필요한 슬라이더·진행률 |
| Ease | 시작·종료가 부드러워야 하는 위치·스케일 |
| Hold | 라벨 상태·단계 유지 |
| Motion Blur | 실제 움직이는 그래픽에만 적용 |
| Graph Editor | 급격한 overshoot·정지·튀는 속도 제거 |
