# ComfyUI Pipeline (AE ↔ ComfyUI 왕복)

AE만으로 만들 수 없는 생성형 단계가 있습니다: 물체 제거·교체, 리라이트, 화면 밖 확장, 알파 매트 생성, 업스케일, 보간, 영상 연장. 이런 단계는 `comfyui/workflows/`의 ComfyUI 워크플로로 처리하고 결과만 AE로 되돌립니다. ComfyUI 실행 자체는 이 저장소의 AE MCP 범위 밖입니다. 에이전트는 **내보내기 규격 → 워크플로 선택 → 핸드오프 brief → 가져오기 검수**를 담당합니다. 작업별 파일 선택은 [`comfyui/workflows/README.md`](../comfyui/workflows/README.md) 1장을 따릅니다.

## 1. 순서

`AE INSPECT → 구간·규격 확정 → AE에서 소스/마스크/스틸 내보내기 → 워크플로 선택 → handoff brief 작성(templates/comfyui-handoff.md) → ComfyUI 실행(사용자 또는 별도 도구) → 결과 가져오기 → AE RE-INSPECT → RENDER FRAME → VISUAL QC`

생성 결과를 원본 레이어에 덮어쓰지 않습니다. 결과는 새 footage 항목으로 가져와 원본 위 별도 레이어에 둡니다. 원본 레이어는 비활성화만 하고 지우지 않습니다.

## 2. AE에서 내보내기

| 대상 | 형식 | 규칙 |
|---|---|---|
| 원본 플레이트 | ProRes 422 HQ 또는 PNG 시퀀스. HDR·ACES 프로젝트는 EXR | 컴프 해상도·fps 그대로, 처리할 구간만, 손실 큰 H.264 피함 |
| 마스크 (인페인팅·지우개) | 흑백 영상 (흰색 = 바꿀 곳) | 원본과 **같은 W×H·프레임 수·fps·시작 프레임**. 그림자·반사·접촉부 포함. 반대 극성이면 워크플로의 '마스크 반전' 사용 |
| 편집할 첫 프레임 / 앵커 | PNG (컴프 해상도) | 편집 후 구도·비율·크롭이 같아야 함 (Ripple·FFP·Person Remover) |
| 레퍼런스 스틸 | PNG | 투명 배경은 알파 유지 PNG |
| 첫·끝 프레임 (브리지 샷) | PNG 2장 | 같은 해상도 |

## 3. 모델별 시간·크기 제한

| 계열 | 프레임 규칙 | 길이·크기 제한 | AE 쪽 조치 |
|---|---|---|---|
| MiniMax H3 (로컬) | 17k+5 (워크플로가 패딩 후 원본 N으로 복원) | 학습 24fps · 참조 영상 2~15초 · 768p급 내부 추론 | 30/60fps 소스는 24fps로 바꿔 넣는 것을 권장. 결과 fps는 워크플로 노트 확인 |
| LTX-2.5 (로컬) | 8k+1 | 1단계 32배수, 2단계 64배수 · AlphaGen 145프레임 이하 | 긴 컷은 구간을 나눠 처리 |
| Wan VACE / Bernini-R | 워크플로 내부 처리 | 약 81프레임(16fps 학습) 단위 권장 | 구간 분할 |
| MiniMax H3 Max API | — | Insert ≤60초 · Recast 5~30초(한 컷 ≤15초) · Reframe 0.5~300초 · Extend ≤60초 | 결과 길이 변화 확인 (Insert·Extend는 전체 길이가 바뀜) |
| Bria Video Eraser API | — | ≤5.1초 · 20~30fps · 짝수 픽셀 | 결과가 몇 프레임 짧을 수 있음 |

## 4. 결과 가져오기 (Interpret Footage)

| 결과 형식 | 해석 |
|---|---|
| MP4 / MOV | Frame rate = 원본 fps (H3 생성물은 24fps라 컴프와 다르면 의도를 확인) |
| ProRes 4444 MOV (Save Video: format `mov` + codec `prores`) | 알파가 있으면 Straight |
| RGBA PNG 시퀀스 | Import As Sequence · fps 지정 · Alpha = Straight |
| Luma 매트 영상 (흰색 = 전경) | Track Matte = Luma |
| EXR (LTX SDR→HDR, HDR 인페인팅) | 32bpc 프로젝트 · ACEScg(Linear) |

ComfyUI는 v0.44.0부터 Save Video에서 MOV + ProRes(알파 지원 4444 기본)를 저장할 수 있습니다. 압축 손실 없이 AE로 넘기려면 워크플로 끝의 Save Video 형식을 `mov / prores`로 바꾸도록 brief에 적습니다(Comfy Cloud가 해당 버전인지 확인).

## 5. QC gate (가져온 뒤)

| Gate | 통과 기준 |
|---|---|
| 규격 | 결과 W×H·프레임 수·fps가 brief와 일치. 다르면 원인(API 길이 변화·패딩 복원 실패)을 기록 |
| 정렬 | 원본과 Difference 모드로 첫·중간·끝 프레임 비교 시 보호 영역이 검정에 가까움 |
| 경계 | 마스크 경계에 halo·삐침·검은 테두리 없음 (필요 시 AE에서 결과를 마스크로 다시 제한) |
| 색 | 보호 영역의 색 이동 없음. 리라이트·HDR은 의도한 변화만 |
| 시간 | 깜빡임·튐 없음. 생성 구간 앞뒤 1초를 프레임 단위로 확인 |
| 소리 | 무음 출력 워크플로는 AE에서 원본 오디오 유지 |

## 6. 기록과 안전

- 변경 로그에 남길 것:
  - 워크플로 파일 경로와 날짜 (예: `comfyui/workflows/H3/05b_…json`)
  - 바꾼 위젯 값
  - 시드
  - 모델 파일명 (로더 값 그대로)
  - 입력·출력 파일 경로
- **유료 API** (`comfyui/workflows/유료API/`)
  - 크레딧이 차감되고 소스가 외부 서비스로 업로드됩니다.
  - 실행 전 범위·예상 비용·업로드 허용 여부를 사용자에게 확인합니다.
- **Recast(인물 교체)**: 레퍼런스 인물의 초상 사용 동의가 확인된 경우에만 brief에 넣습니다.
- 모델 이름: Comfy Cloud에서 가져오기한 모델은 `소유자__저장소__파일명` 형식이고 저장소 이름의 점은 빠집니다. 이름을 추측해 바꾸지 말고 [`comfyui/MODELS.md`](../comfyui/MODELS.md)의 로더 값을 씁니다.
- 생성 결과가 원본 픽셀을 보존한다고 가정하지 않습니다. 마스크 밖 보존이 필요한 샷은 AE에서 결과를 마스크로 제한해 합성합니다.
