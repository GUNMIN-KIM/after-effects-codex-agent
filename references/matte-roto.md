# Matte, Roto, and Edge

Alpha는 투명도, Luma는 밝기, Mask는 한 레이어의 경로, Track Matte는 다른 레이어 정보를 이용한 가시성 제한이다. 투명 소스는 Alpha Matte를 우선 검토하고, 흑백 밝기 소스는 Luma Matte를 검토한다. 반전은 테스트 프레임에서 피사체가 실제로 보이는지 확인한 뒤 사용한다.

로토는 머리카락·손가락·반투명 영역을 별도 검수한다. Feather와 Choke는 최소값부터 조정하고, edge blur로 문제를 숨기지 않는다. 빠른 움직임에서는 motion blur와 로토 경계가 혼동되지 않도록 원본, matte, composite를 번갈아 본다.

| 증상 | 원인 후보 | 조치 |
|---|---|---|
| 피사체 소실 | Alpha/Luma 오선택 또는 반전 | 채널 보기와 matte mode 재확인 |
| 검은 후광 | premultiplied 해석 불일치 | footage interpretation과 choke 점검 |
| 가장자리 떨림 | 로토 key 부족 또는 시간축 불일치 | 문제 구간 key를 추가하고 프레임 정렬 |
| 배경 누출 | 마스크 feather 과다 | 경로와 feather를 실제 윤곽에 맞춤 |
