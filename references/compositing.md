# Compositing

합성은 소스 정렬, 변환, 마스크, 블렌딩, 광원, 질감 순서로 설계한다. 원본과 VFX는 같은 시간축·프레임레이트·픽셀 종횡비를 사용해야 한다. Perspective나 Depth가 필요한 경우 2D 스케일만 조정하지 말고 카메라·트래킹·소실점의 근거를 먼저 확인한다.

권장 순서는 `source alignment → transform → matte/mask → base color → shadow/contact → light wrap → grain → final glow`다. Light Wrap은 피사체 가장자리와 배경의 광원 방향이 일치할 때만 약하게 적용하고, Grain은 마지막 단계에서 전체 샷의 질감으로 통일한다. 블렌딩 모드와 opacity를 임의로 바꾸지 말고 전후 프레임으로 확인한다.

| 점검 | 기준 |
|---|---|
| 정렬 | 눈·손·윤곽 등 기준점이 원본과 일치 |
| 깊이 | 피사체 앞뒤 관계와 그림자 방향이 일관됨 |
| 광원 | 하이라이트·반사·Light Wrap 방향이 동일 |
| 질감 | 노이즈 크기와 색상이 레이어마다 따로 보이지 않음 |
| 가장자리 | halo, fringe, premultiplied 검은 테두리 없음 |
