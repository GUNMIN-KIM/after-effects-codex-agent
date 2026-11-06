# ComfyUI VFX 워크플로 팩 · 2026-11-06 업데이트

After Effects 합성 작업에 넣을 플레이트·매트·편집 영상을 만드는 ComfyUI 워크플로 모음입니다. 모든 영상 워크플로는 **원본 가로×세로·프레임 수·FPS를 그대로 돌려주는 것**을 기본 규칙으로 합니다. 예외는 각 파일 노트에 적혀 있습니다(생성형 길이 변경, API 결과 프레임 부족 등).

- 실행 환경: Comfy Cloud(주 사용) 또는 로컬 ComfyUI **v0.44.0 이상**. p-h3-image와 H3 잠재 업스케일러는 v0.44.x 노드라서 그 이전 버전에서는 노드가 없다고 나옵니다.
- 모델 이름 규칙: 각 파일 노트의 **모델** 표와 노드의 다운로드 정보(`properties.models`)는 실제 로더 값과 같습니다. 이번 업데이트에서 이름이 달랐던 곳을 모두 맞췄습니다(아래 변경 내역).
  - **Cloud 이름**: 라이브러리에 없어 가져오기(import)한 모델은 `소유자__저장소__파일명`이 됩니다. 저장소 이름의 점은 빠집니다(예: `Lightricks/LTX-2.5-22b-…` → `Lightricks__LTX-25-22b-…__…`).
  - **로컬**: 노드의 '누락 모델 다운로드'를 쓰면 위 이름 그대로 저장되어 바로 맞습니다. 직접 받았다면 파일 이름을 로더 값과 같게 바꾸거나 로더에서 다시 고르세요.
- 프롬프트: [`H3_프롬프트_가이드.md`](H3_프롬프트_가이드.md) (MiniMax H3 계열, 이번에 10장 추가) · [`LTX25_프롬프트_가이드.md`](LTX25_프롬프트_가이드.md) (신규) · [`qwen/얼어붙은호텔_프롬프트예시.txt`](qwen/얼어붙은호텔_프롬프트예시.txt)

---

## 1. 무엇을 쓸까 (작업 → 파일)

| 하고 싶은 것 | 1순위 | 대안 / 비교 |
|---|---|---|
| 문장으로 영상 편집 (대상 교체·추가·스타일) | `H3/01_H3_VFX_Edit` | `LTX2.5/01_EditAnything` · `H3/02_R2V`(LoRA 없음) · `WAN/Bernini-R`(참조 이미지) |
| 첫 프레임(또는 아무 프레임)을 고쳐서 영상 전체에 전파 | `H3/05b_Ripple_PikaFlex` (새 공식 조합) | `H3/05_Ripple`(Turbo · Cloud GPU 검증) · `H3/03_VFX_FFP` · `LTX2.5/02_Ripple` |
| ↳ 그 편집 프레임 만들기 | `이미지편집/p-h3-image_첫프레임·앵커편집` **(신규)** | `qwen/Qwen2.1-Turbo_이미지편집` |
| 원본을 밑그림으로 룩만 다시 그리기 | `H3/04_V2V` · `LTX2.5/03_V2V` | — |
| 마스크 영역 교체·제거 | `인페인팅/H3_…FunControlNet2.0` · `인페인팅/LTX25_…참조첫프레임` | `WAN/VACE` 2종 · **EXR 플레이트**: `인페인팅/LTX25_인페인팅_HDR_EXR시퀀스` **(신규)** · 유료: `유료API/Bria_영상지우개` **(신규)** |
| 마스크 없이 사람·차량 지우기 (클린 플레이트) | `제거/ltx/LTX2.5_클린플레이트` | `제거/h3/H3_인물제거_SAM3자동추적` |
| NG 구간만 다시 만들기 (시간축) | `유료API/H3Max_구간교체_Insert` **(신규)** | 로컬: 앞뒤를 `프레임보간/…영상연장`으로 잇기 |
| 화면 밖 확장 · 화면비 변경 | `아웃페인팅/H3_…` · `아웃페인팅/LTX2.5_…` | 유료: `유료API/H3Max_화면비확장_Reframe` **(신규)** |
| 영상 길이 늘리기 | `프레임보간/ltx/LTX2.5_영상연장` (원본 해상도) · `프레임보간/h3/H3_영상연장` | 유료: `유료API/H3Max_영상연장_Extend` **(신규)** |
| 프레임 보간 · 슬로모션 | `프레임보간/rife/…길이동일` (원본 프레임 유지) | `프레임보간/ltx/…슬로모션x2`(큰 동작) · `프레임보간/rife/…문제프레임만` |
| 알파 매트 · 로토 | `로토/LTX2.5_알파매트_AlphaGen` (반투명 경계) · `로토/SAM3.1_로토매트` (추적) | 유료: `유료API/Bria_투명배경_RGBA·매트` **(신규)** · 스틸: `로토/Qwen2.1_배경제거_RGBA_PNG` **(신규)** |
| 깊이·노멀·라인·포즈 패스 | `로토/ControlNetAux_…패스` | `로토/SAM3D-Body_프리비즈`(3D 포즈) |
| 구조(깊이·캐니·포즈) 유지하며 실사화 | `LTX2.5/05_UnionControl` **(신규)** | — |
| 낮 → 밤 리라이트 | `LTX2.5/04_DayToNight_리라이트` **(신규)** | — |
| 업스케일 · 복원 | `업스케일/seedvr2/…비디오` (원본 보존) | `업스케일/ltx/LTX2.5_디테일리파인_TiledFusion` **(신규)** · 유료: `유료API/H3_2K재렌더` **(신규)** · 로컬 RTX: `업스케일/rtx` |
| SDR → HDR (EXR 마스터) | `업스케일/ltx/LTX2.5_SDR→HDR_EXR·HLG` **(신규)** | `업스케일/rtx/RTX_HDR_10bit_HQ` (RTX GPU 로컬) |
| 두 프레임 사이를 잇는 브리지 샷 | `H3/06_PikaFlex_첫끝프레임` **(신규)** | — |
| 레퍼런스(인물·소품·장소)로 인서트 컷 생성 | `H3/07_PikaFlex_레퍼런스` **(신규)** | `H3/08_FastH3_OmniRef` **(신규)** |
| 애니매틱 스틸 여러 장 → 영상 | `H3/09_멀티프레임_키프레임가이드` **(신규)** | — |
| 스틸 → 카메라 무브 | `유료API/H3Max_카메라컨트롤` **(신규)** | — |
| 출연자 교체 (초상 동의 필수) | `유료API/H3Max_인물교체_Recast` **(신규)** | — |

---

## 2. 변경 내역 (2026-11-06)

### 수정 (기존 파일)
| 파일 | 문제 | 조치 |
|---|---|---|
| `H3/01_H3_VFX_Edit_텍스트편집` | 실행값은 vfx_edit r128인데 안쪽 로더와 다운로드 정보는 style_transfer로 남아 있었음. 로컬 '누락 모델'로 다른 파일을 받게 됨 | 안쪽 값, 중첩 서브그래프, 다운로드 정보, extra 기록을 vfx_edit r128로 통일 |
| `H3/03_H3_VFX_FFP_첫프레임전파` | 로더 4개 모두 다운로드 정보 없음 | 정보 추가 |
| `LTX2.5/01_LTX25_EditAnything` | 프롬프트 강화 모델과 LoRA의 실행값(Cloud 이름)이 안쪽 값·다운로드 정보와 다름 | 통일. 2단계 시그마 0.85 → **0.909375** (Lightricks 공식) |
| `LTX2.5/02_LTX25_Ripple` | 다운로드 정보가 원래 파일명이라 받아도 '모델 없음' | 정보 이름을 로더 값과 일치시킴 |
| `제거/ltx/LTX2.5_클린플레이트` | 같은 이름 불일치 | 정보 이름 일치. 원본 저장소 표기 교정 |
| `WAN/WAN2.2-FunVACE_인페인팅` | 안쪽 고노이즈 UNET이 **Wan2.1 VACE**로 남아 있음. 모델 링크 노트도 2.1 VACE·CausVid로 잘못 적힘 | 2.2 Fun VACE 고노이즈로 교정. 노트를 실제 모델(Fun VACE 고·저 + Lightning 250928)로 교체 |
| `WAN/WAN2.2_Bernini-R` | lightx2v 4스텝 LoRA 2개의 다운로드 정보 없음 | 정보 추가 (Comfy-Org 공식 경로) |
| `프레임보간/ltx/LTX2.5_영상연장` | 2단계 시그마 0.85 | **0.909375**로 교체 (Lightricks 공식) |
| `프레임보간/rife/RIFE4.26_프레임보간_길이동일` | 로더 다운로드 정보 없음 | 정보 추가 |

### 추가 (신규 20개)
- **H3 오픈 웨이트**
  - `05b`: Ripple + Pika Flex 6스텝. 제작자가 11-05에 공식 워크플로를 이 조합으로 바꿈.
  - `06`: Pika Flex 첫·끝 프레임.
  - `07`: Pika Flex 레퍼런스.
  - `08`: FastH3 OmniRef 8스텝.
  - `09`: 멀티프레임 키프레임 가이드.
  - `이미지편집/p-h3-image`: 11-03 공개된 H3 기반 이미지 편집 모델.
- **LTX-2.5** (Lightricks 공식 그래프에 한국어 안내 추가)
  - Day-To-Night 리라이트
  - Union Control
  - Refine-Details 업스케일
  - SDR→HDR (EXR)
  - 인페인팅 HDR (EXR)
- **로토**: Qwen 2.1 배경 제거 (RGBA PNG)
- **유료 API** (`유료API/`)
  - MiniMax H3 Max: Insert(구간 교체), Extend, Reframe, Recast, Camera Control
  - H3 Regenerate 2K
  - Bria: Video Eraser(마스크 인페인팅), 투명 배경
- **문서**: `LTX25_프롬프트_가이드.md` 신규. `H3_프롬프트_가이드.md`에 10장 추가.

### 바꾸지 않은 것
- 모든 기존 파일의 그래프 구조, 연결, 출력 규격, 시드 기본값은 그대로입니다. 위 표의 값만 바꿨습니다.
- `NSFW/` 폴더는 검토·수정 대상에서 제외했습니다. 파일은 원본 그대로이고, 공개 저장소 사본에는 넣지 않았습니다.
- 결과 영상·대조시트(`*.mp4`, `*.jpg`)는 zip 패키지에만 있고 저장소에는 넣지 않았습니다.

---

## 3. 모델 최신 현황 (2026-11-06 확인)

| 계열 | 이 팩에서 쓰는 것 | 최신 상태 | 조치 |
|---|---|---|---|
| MiniMax H3 본체 (ref2va / fl2va pruned int8) | ✔ | 새 버전 없음 (H3.1·Pro·인페인트 체크포인트 없음) | 유지 |
| H3 Fun ControlNet Union | 2.0 | **2.0이 최신** | 유지 |
| H3 Turbo (lightx2v) | fl2v 8step v1.1 · 4step v1.3 | 둘 다 최신. ref2v 8step v1.1 768p도 공개됨 (미검증) | 유지. 768p 터보는 시프트 6/3 (`H3/04` 이미 적용) |
| H3 가속 신규 | — | **Pika H3 Flex** (fl2va·ref2va, 6스텝) · **FastH3** (OmniRef·V2, 8스텝) · ref2v turbo 4step v0.1 (공식) | `05b` `06` `07` `08` `09` 추가 |
| H3 커뮤니티 LoRA | VFX Edit·FFP·Style v1.0, Ripple v1, Person Remover V1 | 모두 최신. 신규: Alissonerdx LMS(디테일)·Character Swap v1.1·Head Swap (미검증) | 유지 |
| H3 VAE | video int8/fp16, audio fp32 | 선택 디코더 신규: **Sol-H3-VAE**(빠른 전체 디코드) · LightVAE (파일명 미검증) | 문서만 |
| H3 신규 노드 | — | `MiniMaxH3LatentUpscaleWithModel` (10-28) · `MiniMaxH3ContextWindows` (긴 영상, 10-30) · `PH3ImageConditioning` (11-03) | p-h3-image만 추가. 업스케일러 모델은 커뮤니티 파일이라 보류 |
| LTX-2.5 본체·VAE·Gemma·업스케일러 | ✔ | 새 버전 없음 (LTX-2.6/3 없음). `gemma4_e2b_it_int8_convrot`(가벼운 프롬프트 강화) 있음 | 유지 |
| LTX 인/아웃페인팅 IC-LoRA | 2.3 in-outpainting 0.9 | **2.5 전용 없음**. Lightricks 2.5 공식 그래프도 2.3 파일 사용 | 유지 |
| LTX-2.5 IC-LoRA 신규 | Alpha-Gen 0.9 · Clean-Plate 1.0 | **Day-To-Night 0.9 · SDR-To-HDR 1.0 · Refine-Details 1.0 · Pixel-Spatial-Upscaler x2 1.0** | 4종 그래프 추가 (Pixel 업스케일러 제외) |
| EditAnything · LTX-Ripple | v2 · v11 | 최신 | 유지 |
| Wan | 2.1 VACE · 2.2 Fun VACE · Bernini-R · Lightning 250928 | 오픈 웨이트 신버전 없음 (Wan 2.7·3.0은 API 전용) | 유지 |
| Qwen-Image | 2.1 Turbo | 2.1이 최신 오픈 웨이트 (3.0은 API 전용) | 배경 제거 추가 |
| SeedVR2 · RIFE · SAM 3.1 | ✔ | 모두 최신 (RIFE 4.27·SAM 3.2·SeedVR3 없음). `seedvr2_7b_sharp_fp16` 있음 | 유지 |
| MoGe · Depth | MoGe-2 · DA V2 | **MoGe-3** · **Depth Anything 3**(코어 내장) 신규 | 문서만 |
| RTX VFX 노드 | 0.2.1 | 0.2.1이 최신. 저장소 이름이 `ComfyUI_Nvidia_VFX_Nodes`로 바뀜. `RTXVideoFrameGeneration` 추가됨 | 유지 |

**미검증 표시 기준**
- 공식 템플릿이나 공식 그래프에 정확한 다운로드 URL이 있는 파일만 워크플로에 넣었습니다.
- 검색 결과로만 본 파일은 "미검증"으로 표시하고 넣지 않았습니다. 이 환경에서는 Hugging Face 접속이 막혀 파일 목록을 직접 열 수 없었습니다.
- 커뮤니티 LoRA 다운로드 경로 일부(Alissonerdx `loras/…`, ethanfel Qwen3-VL-4B)는 기존 팩의 경로 규칙을 따랐습니다. 처음 받을 때 404가 나면 해당 저장소 파일 목록에서 경로를 확인하세요.

---

## 4. 검증 상태

| 항목 | 결과 |
|---|---|
| JSON 구조·링크 (워크플로 55개 = 기존 35(NSFW 3 포함) + 신규 20 · 저장소 사본 52개) | 정적 검사 통과 (끊긴 링크 0, 정의되지 않은 서브그래프 0 · 선택 입력 미연결만 있음) |
| 노드 존재 | 최신 ComfyUI master(2026-11-06) + KJNodes + LTXVideo + VHS + controlnet_aux 소스와 대조 → 모두 존재. 예외는 RTX 전용 팩과 Video Depth Anything 팩(`LTX2.5/05` 깊이 주석기), 둘 다 별도 설치 필요 |
| 모델 이름 ↔ 다운로드 정보 | 비 NSFW 전 파일에서 일치 |
| GPU 실행 | **이번 업데이트에서는 실행하지 않음.** `H3/05`만 이전 Cloud GPU 검증(11-05) 상태. 신규 파일은 처음에 짧은 구간·고정 시드로 확인하세요 |
| 유료 API | 크레딧 실행 안 함. Reframe·Recast·Camera는 공식 템플릿 구조. Insert·Extend·2K·Bria 2종은 노드 스키마(입력·위젯 순서)를 보고 구성 |

---

## 5. 출처
- ComfyUI 소스: `Comfy-Org/ComfyUI` master `63e5bf5` (2026-11-06). 커스텀 노드: `ComfyUI-LTXVideo` `220e1d4`, `ComfyUI-KJNodes` `ab72eda`
- 공식 템플릿: `comfyui-workflow-templates-json` 0.1.129 (MIT)
- Lightricks LTX-2.5 example_workflows: LTX-2 Community License (원문은 저장소 `comfyui/licenses/` 참고)
- 모델 카드: MiniMaxAI/MiniMax-H3, Comfy-Org/MiniMax-H3, Lightricks/LTX-2.5, PrunaAI/p-h3-image-comfy, Pika-Labs/Pika-H3-Flex, FastVideo/FastH3-OmniRef-Comfy
