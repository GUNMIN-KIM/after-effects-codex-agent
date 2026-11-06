# ComfyUI 워크플로 팩

After Effects 작업에 넣을 생성형 단계를 위한 ComfyUI 워크플로 모음입니다(편집·제거·인페인팅·아웃페인팅·매트·업스케일·보간·연장). AE와의 왕복 규칙은 [`../references/comfyui-pipeline.md`](../references/comfyui-pipeline.md), 작업 지시는 [`../templates/comfyui-handoff.md`](../templates/comfyui-handoff.md)에 있습니다.

| 경로 | 내용 |
|---|---|
| [`workflows/README.md`](workflows/README.md) | 작업별 선택표 · 변경 내역 · 모델 최신 현황 · 검증 상태 |
| `workflows/<분류>/…json` | ComfyUI UI 형식 워크플로 (Comfy Cloud / 로컬 ComfyUI ≥ v0.44.0). 각 파일에 한국어 사용 안내 노트 포함 |
| [`workflows/H3_프롬프트_가이드.md`](workflows/H3_프롬프트_가이드.md) | MiniMax H3 계열 프롬프트 (V2V 편집, Pika Flex, FastH3, p-h3-image, H3 Max API) |
| [`workflows/LTX25_프롬프트_가이드.md`](workflows/LTX25_프롬프트_가이드.md) | LTX-2.5 편집·IC-LoRA 프롬프트 |
| [`MODELS.md`](MODELS.md) | 모든 워크플로가 참조하는 모델 파일 (로더 값 · 폴더 · 다운로드 URL) |
| `licenses/` | 재배포한 Lightricks 예제 그래프의 라이선스 원문 |

## 분류

| 폴더 | 내용 |
|---|---|
| `H3/` | MiniMax H3 영상 편집 계열 (VFX Edit, R2V, FFP, V2V, Ripple, Pika Flex, FastH3, 멀티프레임) |
| `LTX2.5/` | LTX-2.5 편집 계열 (EditAnything, Ripple, V2V, Day-To-Night, Union Control) |
| `WAN/` | Wan 2.1 VACE · 2.2 Fun VACE 인페인팅, Bernini-R |
| `qwen/` · `이미지편집/` | 스틸 편집 (Qwen-Image 2.1 Turbo, p-h3-image) |
| `인페인팅/` · `아웃페인팅/` · `제거/` | 마스크 교체 · 화면 밖 확장 · 클린 플레이트 |
| `로토/` | 알파 매트, SAM 3.1 추적, 깊이·노멀 패스, 3D 포즈, 배경 제거 |
| `업스케일/` | SeedVR2, Z-Image 리파인, RTX VSR/HDR, LTX 디테일 리파인, SDR→HDR |
| `프레임보간/` | RIFE, LTX 슬로모션, 영상 연장 (H3·LTX) |
| `유료API/` | MiniMax H3 Max (Insert·Extend·Reframe·Recast·Camera), H3 2K, Bria (Video Eraser·투명 배경) |

## 원칙

- 원본 가로×세로·프레임 수·FPS를 그대로 돌려주는 것이 기본입니다. 예외(생성형 길이 변경, API 결과 길이 차이)는 각 노트에 적혀 있습니다.
- 모델 파일명은 로더 값과 다운로드 정보가 일치해야 합니다. Comfy Cloud에서 가져오기한 모델은 `소유자__저장소__파일명` 형식이고, 저장소 이름의 점은 빠집니다.
- GPU 실행 검증 여부는 파일마다 다릅니다. [`workflows/README.md`](workflows/README.md) 4장과 각 노트의 '검증' 항목을 확인하세요.
- 공개 저장소에는 결과 영상·대조시트 이미지와 성인용 워크플로를 넣지 않습니다.
