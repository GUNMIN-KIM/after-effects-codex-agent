# ComfyUI Handoff Brief

## 샷
- AE 프로젝트 / 컴포지션: 
- 레이어 (stable ID · 이름): 
- 처리 구간 (컴프 시간코드 · 소스 프레임): 
- 해상도 / fps / 프레임 수 / 색상 공간: 

## 작업
- 목적 (한 문장): 
- 워크플로: `comfyui/workflows/…json` (선택 이유: `comfyui/workflows/README.md` 1장)
- 로컬 / Comfy Cloud / 유료 API: 
- 유료 API일 때: 예상 비용 · 업로드 허용 확인 (예/아니오)

## 입력 (AE에서 내보낸 파일)
| 입력 | 파일 경로 | 형식 | W×H · 프레임 · fps |
|---|---|---|---|
| 원본 |  |  |  |
| 마스크 (흰색 = 바꿀 곳) |  |  |  |
| 편집 첫 프레임 / 앵커 / 레퍼런스 |  |  |  |

## 설정
- 프롬프트 (영어 · `H3_프롬프트_가이드.md` / `LTX25_프롬프트_가이드.md` 형식): 
- 바꾼 위젯 값: 
- 시드 (fixed): 
- 저장 형식 (Save Video `mov/prores` 권장 · 알파 필요 시 RGBA PNG): 

## 되돌려 받을 것
- 결과 파일 경로: 
- 예상 규격 (W×H · 프레임 · fps · 길이 변화 여부): 
- AE 배치: 새 레이어로 원본 위 · 같은 in-point · Interpret Footage 설정: 

## QC (`references/comfyui-pipeline.md` 5장)
- [ ] 규격 일치  - [ ] 보호 영역 Difference  - [ ] 경계  - [ ] 색  - [ ] 시간(깜빡임)  - [ ] 소리
