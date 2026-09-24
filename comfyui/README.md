# ComfyUI LTX 워크플로 (LTX-2.5 기준 · 2026-09)

After Effects 합성 전에 ComfyUI에서 쓰는 영상 생성 워크플로 4종이다. 기존 워크플로(`legacy/`)를 Lightricks 공식 LTX-2.5 그래프와 LTX-2 코드 기준으로 다시 구성했다.

| 파일 | 용도 | 기반 모델 | 핵심 변경 |
|---|---|---|---|
| `workflows/LTX2.5_Extend_Retake.json` | 길이 연장 | 2.5 distilled | 원본 마지막 2초를 latent에 **고정**하고 뒤만 생성 (Retake 방식) |
| `workflows/LTX2.5_Outpaint_Original1to1.json` | 아웃페인트 | 2.5 distilled + 2.3 In/Outpaint IC-LoRA | 공식 2-stage 구조 + **Laplacian 블렌드**로 원본 1:1 복원 |
| `workflows/LTX2.5_CleanPlate.json` | 사람·차량 제거 | 2.5 distilled + **2.5 Clean Plate IC-LoRA** | 2.3에서 2.5 전용 LoRA로 교체 + 2-stage |
| `workflows/LTX2.5_UnionControl_MoGe.json` | 깊이 제어 v2v | 2.5 distilled + 2.3 Union IC-LoRA | 공식 sigma, 2-stage, 제어 영상 비율·fps 자동 |

### 구조: 메인 그래프 + CORE 서브그래프
각 워크플로를 열면 메인 화면에는 아래 네 가지만 보인다.

| 메인 그래프 | 내용 |
|---|---|
| 조작 패널 | 입력 영상, 프롬프트, ①~⑩ 설정값 |
| 모델 | 트랜스포머, IC-LoRA, 텍스트 인코더, VAE, 업스케일러 로더 — 파일명을 여기서 바로 바꾼다 |
| **CORE 서브그래프** | `LTX-2.5 … CORE (더블클릭=내부 진입)` — 처리 엔진 전체 |
| 출력 | MP4 / ProRes / 미리보기 |

CORE를 더블클릭하면 안에 그룹별로 정리된 엔진이 있다: 자동 계산 → 준비 → Stage 1 → Stage 2 → 후처리. 서브그래프 입력 이름은 연결된 조작 패널 노드 이름(①, ② …)과 같다. 평소에는 메인의 ①~⑩ 값만 바꾸면 된다.

| 워크플로 | CORE 이름 | CORE 내부 노드 | 입력 / 출력 |
|---|---|---|---|
| 길이 연장 | LTX-2.5 EXTEND CORE | 60 | 19 / 3 |
| 아웃페인트 | LTX-2.5 OUTPAINT CORE | 61 | 17 / 3 |
| Clean Plate | LTX-2.5 CLEANPLATE CORE | 39 | 15 / 3 |
| Union | LTX-2.5 UNION CONTROL CORE | 47 | 18 / 5 |

---

## 1. 2.3과 2.5 중 어느 쪽을 쓰나

| 작업 | 선택 | 근거 |
|---|---|---|
| 길이 연장 | **2.5** | IC-LoRA가 필요 없는 기본 모델 기능이다. 2.5가 최신 기본 모델이고 공식 Comfy 템플릿도 2.5 기준이다. |
| 아웃페인트 | **2.5 + 2.3 LoRA** | 2.5 전용 In/Outpaint LoRA는 아직 없다. Lightricks 공식 `LTX-2.5_ICLoRA_Outpaint_Two_Stage_Distilled.json`도 2.5 distilled에 `ltx-2.3-22b-ic-lora-in-outpainting-0.9`를 얹는다. |
| Clean Plate | **2.5** | 2.5에서 따로 학습한 공식 `LTX-2.5-22b-IC-LoRA-Clean-Plate`가 나왔다. |
| Union Control | **2.5 + 2.3 LoRA** | 공식 `LTX-2.5_ICLoRA_Union_Control_Distilled.json`이 같은 조합을 쓴다. |

> LTX-2 README에는 "LoRA는 학습에 쓴 모델에서만 동작한다"는 문장이 있다. 그런데 공식 2.5 예제 워크플로가 2.3 IC-LoRA를 그대로 쓰므로 IC-LoRA는 예외로 보고 공식 예제를 따랐다. 2.5 전용판이 나오면 로더의 파일명만 바꾸면 된다.

### A/B 비교 방법 (2.3이 더 나은 경우 판단용)
1. `legacy/LTX2.3_CleanPlate_원본.json`과 `workflows/LTX2.5_CleanPlate.json`에 **같은 클립, 같은 seed**를 넣는다.
2. 첫 프레임, 중간 프레임, 마지막 프레임을 After Effects에서 원본 위에 Difference 모드로 겹쳐 비교한다.
   - 사람 잔상
   - 배경 디테일
   - 색 차이
3. 2.3이 낫다면 2.3 파일을 계속 쓴다. 2.3 원본은 `TwoWaySwitch`(controlaltai-nodes)를 쓰고 VHS `LTXV` 포맷이 해상도와 프레임을 자르므로, 그 두 가지를 감안해서 비교한다.

**주의:** 이 저장소 작업 환경에는 GPU가 없어 실제 생성 품질 비교는 하지 못했다. 위 판단은 공식 문서와 공식 예제를 근거로 한 것이다.

---

## 2. 워크플로별 원리

### 길이 연장 — `LTX2.5_Extend_Retake.json`
기존 방식은 마지막 9프레임을 `LTXVAddGuide`(strength 1.15)로 참고시키는 것이었다. 모델이 얼굴을 9프레임만 보고 다시 그리기 때문에 얼굴이 뭉개졌다. 새 방식은 다음과 같다.

1. 원본 **마지막 C프레임**(기본 49 ≈ 2초)을 `LTXVImgToVideoInplace`로 latent 앞부분에 넣고 noise mask를 0으로 둔다. 이 구간은 **재생성하지 않는다**.
2. `LTXVSetAudioVideoMaskByTime`(LTXVideo 팩의 Retake용 노드)으로 영상은 문맥 구간을 고정하고 이후만 생성한다. 오디오는 공식 템플릿처럼 영상과 함께 전체를 생성한다.
3. **Stage 1**은 절반 해상도에서 공식 distilled sigma 8개로 생성한다. **Stage 2**는 공식 latent 업스케일러 x2를 거친 뒤 문맥을 풀해상도로 다시 고정하고 3 step으로 정제한다. 얼굴 디테일은 이 단계에서 살아난다.
4. 새 프레임을 **원본 마지막 프레임 색에 맞춘다** (`ColorMatchV2` mkl, 기본 0.5).
5. 원본 프레임은 한 장도 바꾸지 않는다. 이음새는 4프레임 크로스페이드로 처리하고, 최종 크기는 원본 가로·세로로 정확히 복원한다.
6. `force_rate 0`으로 원본 fps를 유지한다. 기존에는 24fps로 강제 변환했다.
7. 소리: 원본 소리를 원본 영상 길이에 정확히 맞춘 뒤(길거나 짧아도 정렬), 연장 구간에는 LTX가 생성한 소리를 붙인다.
   - ⑦ 연장 구간 소리 생성: 끄면 원본 소리 + 연장 구간 무음 (생성 오디오를 전혀 쓰지 않음)
   - ⑪ 원본 영상에 소리 트랙이 있음: 소리 트랙이 없는 영상이면 꺼야 한다 (켜 두면 VHS가 오디오를 읽다가 멈춘다)

> **2026-09 수정 (AAC `NaN/Inf` 오류):** 첫 버전은 원본 소리를 인코드해 문맥으로 고정했는데, 공식 템플릿에 없는 이 경로에서 최종 MP4 인코딩 중 `Input contains (near) NaN/+-Inf` 오류가 보고됐다. 이 경로를 제거했다. 같은 오류가 다시 나면 ⑦을 끄면 된다 (생성 오디오를 쓰지 않으므로 NaN이 들어갈 곳이 없다).

얼굴이 흔들리면 다음 순서로 조정한다.
- ④ 문맥을 73 또는 97로 늘린다.
- ② 프롬프트에 인물 외형을 구체적으로 쓴다.
- 한 번에 3~5초씩 나눠서 연장한다.

### 아웃페인트 — `LTX2.5_Outpaint_Original1to1.json`
- dev 트랜스포머 + distilled LoRA 조합을 **distilled 트랜스포머**로 바꿨다. 공식 IC-LoRA 파이프라인은 distilled 모델만 지원한다.
- **공식 2-stage**로 구성했다.
  1. 절반 해상도에서 8 step으로 생성한다.
  2. 원본 영역을 Laplacian 블렌드로 복원한다.
  3. 확대한 뒤 다시 인코드한다.
  4. sigma `0.725, 0.4219, 0`으로 정제한다.
- **Stage 2에서 원본 영역을 latent로 고정**한다 (`LTXVSetAudioVideoMaskByTime`의 `spatial_mask`: 원본 영역 0, 바깥 1). 첫 버전은 Stage 2가 원본 영역까지 화면 전체를 다시 생성해서, 바깥 영역이 "다시 그려진 가운데"에 맞춰지고 진짜 원본을 붙이면 **원본과 생성 영역이 따로 노는** 문제가 있었다. 이제 바깥 영역은 실제 원본 토큰을 보면서 정제된다.
- 마지막 합성의 딱딱한 `ImageCompositeMasked` 대신 **`LTXVLaplacianPyramidBlend`**를 쓴다. 원본 영역의 고주파 디테일은 그대로 두고, 경계의 저주파(색·밝기)만 이어지므로 경계의 색 단차가 사라진다.
- 생성 영역 전체 색을 원본에 맞춘다. 재생성된 중앙부와 원본 중앙부의 차이를 기준으로 삼는다.
- `RTXVideoSuperResolution`과 `Float32ColorCorrect`를 제거했다. 표준 ComfyUI에는 없는 노드다.
- 원본 오디오는 모델에 고정 입력(`LTXVSetAudioRefTokens`)하고, 출력에는 원본 파형을 그대로 넣는다.

### Clean Plate — `LTX2.5_CleanPlate.json`
- 모델 구성을 2.5로 바꿨다.
  - LoRA: `ltx-2.5-22b-ic-lora-clean-plate-1.0`
  - 트랜스포머: 2.5 distilled
  - 텍스트 인코더: Gemma 4 12B
  - VAE: 2.5
- LoRA 학습 해상도(1024×576, 49프레임 @25fps) 근처에서 Stage 1을 돌리고, latent x2 → 풀해상도 3 step으로 정제한다. 공식 검증 해상도는 1920×1088이다.
- VHS `LTXV` 포맷 강제 자르기와 controlaltai `TwoWaySwitch` 의존을 제거했다. 출력은 원본 해상도·프레임 수 그대로이고, MP4와 ProRes를 함께 낸다.

### Union Control — `LTX2.5_UnionControl_MoGe.json`
- `KSampler + linear_quadratic` 대신 **공식 distilled sigma**를 쓴다. distilled 모델은 이 sigma 값으로 학습됐다.
- 해상도를 고정 1280×704에서 **제어 영상 비율 자동**으로 바꿨다. 짧은 변 544로 생성한 뒤 x2 해서 최종 1088이 된다. fps도 제어 영상에서 자동으로 가져온다.
- 첫 프레임을 Stage 2에서도 다시 고정해서 인물 외형을 유지한다.
- MoGe-2 깊이 추출은 유지했다. 2048px를 넘으면 자동으로 줄인다.

---

## 3. 필요 파일

### 모델 (Comfy-Org 재패키지 파일명 — 기존 워크플로와 동일)
| 폴더 | 파일 |
|---|---|
| `models/diffusion_models/` | `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` |
| `models/text_encoders/` | `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors`, `gemma4_e2b_it_bf16.safetensors` (프롬프트 보강용) |
| `models/vae/` | `ltx-2.5-video-vae-bf16.safetensors`, `ltx-2.5-audio-vae-bf16.safetensors` |
| `models/latent_upscale_models/` | `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` |
| `models/loras/` | `ltx-2.5-22b-ic-lora-clean-plate-1.0.safetensors`, `ltx-2.3-22b-ic-lora-in-outpainting-0.9.safetensors`, `ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors` |
| `models/geometry_estimation/` | `moge_2_vitl_normal_fp16.safetensors` (Union만) |

bf16 원본(`ltx-2.5-22b-distilled-transformer-bf16.safetensors` 등)을 쓰려면 로더의 파일명만 바꾼다.

### 커스텀 노드
- [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo)
  - `LTXVSetAudioVideoMaskByTime`
  - `LTXVLaplacianPyramidBlend`
  - `LTXVInpaintPreprocess`
  - `LTXICLoRALoaderModelOnly`
  - `LTXAddVideoICLoRAGuide(Advanced)`
  - `LTXVSetAudioRefTokens`
- [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes)
  - `ColorMatchV2`
  - `ImageBatchExtendWithOverlap`
  - `ImagePadForOutpaintTargetSize`
- [ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite)
  - `VHS_LoadVideo`
  - `VHS_VideoCombine`

기존 워크플로에 필요했던 ComfyMath, controlaltai-nodes, RTX Video Super Resolution 노드는 더 이상 필요 없다.

---

## 4. 검증 내역

`tools/`의 스크립트로 다음을 확인했다. 검증 환경은 ComfyUI master 2026-09-24 (`6a103b1`), frontend 1.53.6, CPU다.

| 항목 | 결과 |
|---|---|
| 실제 ComfyUI 프론트엔드에서 로드, 누락 노드 검사 | 4개 모두 누락 0 |
| `graphToPrompt` → 백엔드 `/prompt` 검증 (입력 타입, 콤보 값, 필수 입력) | 4개 모두 통과 |
| 모델 없이 실행 가능한 부분 실제 실행 (VAE 디코드만 가짜 프레임으로 대체) | 4개 모두 성공 |

모델 없이 실행한 구간은 자동 계산, 프레임 자르기·패딩, 색 보정, 크로스페이드, Laplacian 블렌드, 오디오 합치기, MP4/ProRes 인코딩이다. 결과는 다음과 같다.

| 워크플로 | 런타임 확인 결과 |
|---|---|
| 연장 | 48프레임 원본 + 3초(72프레임) → 120프레임, 원본 해상도 128×72 유지, 오디오 포함 |
| 아웃페인트 | 128×72 → 21:9 캔버스 192×128, 원본이 (32, 28)에 1:1로 배치, 48프레임 유지 |
| Clean Plate | 원본 해상도·프레임 수 유지, ProRes 10bit 출력 |
| Union | 128×72 제어 영상 → Stage 1 960×544 → 최종 1920×1088 |

GPU가 없어 **실제 LTX 모델 추론은 돌리지 않았다.** 생성 품질(얼굴 일관성, 색 유지)은 사용자 환경에서 확인해야 한다.

서브그래프 버전도 같은 검증을 모두 다시 통과했고, 추가로 "열기 → 저장 → 다시 열기" 왕복 후에도 연결 오류가 없는 것을 확인했다.

검증 중 발견한 사항: 현재 프론트엔드(1.53.6)의 `convertToSubgraph`는 `ComfyMathExpression`(자동 증가 입력) 노드를 서브그래프로 옮길 때 `values.c` 이후 연결을 한 칸씩 밀어 `expression` 칸에 붙인다. `tools/builder.py`가 변환 직후 입력 순서를 링크 번호에 맞게 재정렬해서 보정한다. 직접 ComfyUI에서 "Convert to Subgraph"를 쓸 때도 같은 증상이 날 수 있으니, 변환 뒤 Math Expression 노드의 연결을 확인한다.

또 현재 프론트엔드(1.53.6)에서 `ResizeImageMaskNode`를 `match size`로 쓰면 동적 입력 연결이 로드 시 끊긴다. Lightricks 공식 Outpaint 예제도 같은 오류가 난다. 그래서 새 워크플로에서는 정적 노드(`MaskToImage` → `ImageScale` → `ImageToMask`)를 쓴다.

### 워크플로 다시 만들기
`tools/wf_*.py`는 실행 중인 ComfyUI 프론트엔드 안에서 노드를 생성하고 직렬화한다. 그래서 위젯 순서와 동적 입력이 ComfyUI가 저장하는 형식과 정확히 같다.
```bash
# ComfyUI를 127.0.0.1:8188에서 실행한 상태에서 (Playwright + Chromium 필요)
python tools/wf_extend.py out.json      # 워크플로 생성
python tools/validate.py out.json       # 프론트엔드 로드 + /prompt 검증
python tools/rt_extend.py               # 모델 없는 구간 실제 실행 (out_extend.api.json 필요)
```
스크립트의 경로(`/opt/cf`, Chromium 경로)는 검증 환경 기준이다. 쓰는 환경에 맞게 바꾼다.

---

## 5. 참고 자료
- [Lightricks/LTX-2](https://github.com/Lightricks/LTX-2)
  - 공식 추론 코드
  - 2.5 모델 목록
  - `RetakePipeline`: 시간 구간만 재생성하고 나머지는 보존
  - 기술 보고서 [arXiv 2601.03233](https://arxiv.org/abs/2601.03233)
- [Lightricks/ComfyUI-LTXVideo `example_workflows/2.5`](https://github.com/Lightricks/ComfyUI-LTXVideo)
  - 공식 2.5 Outpaint, Inpaint, Union, V2V 그래프
  - `looping_sampler.md`: 긴 영상, AdaIN 색 드리프트 방지
- [Lightricks/LTX-2.5 (Hugging Face)](https://huggingface.co/Lightricks/LTX-2.5)
- [LTX-2.5-22b-IC-LoRA-Clean-Plate](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Clean-Plate)
- [LTX-2.3-22b-IC-LoRA-In-Outpainting](https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-In-Outpainting)
- [LTX-2.3-22b-IC-LoRA-Union-Control](https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control)
- [ComfyUI 공식 LTX-2.5 템플릿](https://docs.comfy.org/tutorials/video/ltx/ltx-2-5) (`video_ltx2_5_i2v.json`: 2-stage sigma, int8 파일명)
- [color-matcher (MKL, Pitié et al.)](https://github.com/hahnec/color-matcher): `ColorMatchV2`의 색 전이 알고리즘
