# Color, DI, and Glow

색상 작업은 입력 색상 공간 확인 후 노출, 화이트밸런스, 대비, 색조, 스타일 효과 순서로 진행한다. 먼저 원본의 디테일과 피부톤을 보존하고, 그 다음 전체 룩을 적용한다. 여러 샷은 neutral reference를 정해 exposure·WB·contrast를 맞춘 뒤 스타일을 통일한다.

권장 effect order는 `Exposure/Curves → WB → selective color → contrast → grain → glow`다. Glow는 최종 VFX·하이라이트·그래픽처럼 광원이 있어야 하는 요소에 선택적으로 적용한다. Threshold·Radius·Intensity를 크게 올려 색감 문제를 감추지 않는다.

| 목표 | 기준 |
|---|---|
| DI | 블랙 디테일 유지, 하이라이트 클리핑 방지 |
| 피부 | 중립적인 중간톤, 과도한 채도 금지 |
| VFX | 제한된 포인트 컬러, 배경과 분리되는 대비 |
| Glow | 경계가 부풀지 않고 광원 중심만 확산 |
| 납품 | 입력·프로젝트·출력 색상 공간을 기록 |
