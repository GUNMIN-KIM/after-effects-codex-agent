# ComfyUI 워크플로 — 메인 서브그래프 구성

After Effects 합성용 매트·RGBA·3D 소스를 만드는 ComfyUI 워크플로 모음이다. 모든 워크플로는 같은 구조를 따른다.

`입력 (캔버스) → 메인 서브그래프 1개 (처리 + 설정 위젯) → 출력 저장 (캔버스)`

처리 노드는 전부 메인 서브그래프 안에 넣었다. 캔버스에서 직접 써야 하는 노드는 캔버스에 그대로 두었다. 영상 로드, 첫 프레임 Points Editor, Save/Combine 출력 노드, 3D 뷰어가 여기에 해당한다. 서브그래프 노드의 위젯만 바꾸면 주요 설정이 조절된다. 세부 조정은 서브그래프 안으로 들어가서 한다.

## 워크플로 목록

| 파일 | 메인 서브그래프 | 캔버스에 둔 노드 | 설정 위젯 | 출력 |
|---|---|---|---|---|
| `workflows/SAM3.1_FACE_CUTOUT_MAIN_SUBGRAPH.json` | SAM3.1 Face Cutout Main Process (20노드) | LoadVideo, SaveVideo ×3 | prompt, detection_threshold, max_objects, detect_interval, object_indices, mask_expand, tapered_corners, blur_radius, blur_sigma | 검정 배경 얼굴, 소프트 화이트 마스크, 원본 + 화이트 마스크 |
| `workflows/SAM3.1_RGBA_ROTO_MASTER_MAIN_SUBGRAPH.json` | SAM3.1 RGBA Roto Master Main Process (17노드) | VHS LoadVideo / VideoInfo, 시드 프레임, Points Editor, VHS VideoCombine ×5 | seed_threshold, refine_iterations, max_objects, overlay_opacity, qc_fill_color | Alpha, Alpha Invert, Clean RGB, Tracking Overlay (mp4), RGBA ProRes 4444 (.mov) |
| `workflows/SAM3.1_POINTER_MATTE_PACK_MAIN_SUBGRAPH.json` | SAM3.1 Pointer Matte Pack Main Process (23노드) | LoadVideo, GetVideoComponents, 시드 프레임, Points Editor, SaveVideo ×6 | seed_threshold, refine_iterations, cleanup_threshold, edge_grow | BBOX, Alpha, Alpha Invert, 피사체만, 배경만, 원본 + 화이트 마스크 |
| `workflows/SAM3D_BODY_MOGE_GLB_MAIN_SUBGRAPH.json` | SAM3D Body + MoGe Main Process (34노드) | LoadVideo, SaveVideo ×7, SaveGLB ×3, Preview3D ×2 | start_time, duration, prompt, detection_threshold, max_objects, output_width, pose_overlay_strength | 렌더 영상 7종, 포즈 GLB 2종, MoGe 장면 GLB |

Face Cutout은 이미 메인 서브그래프 구조여서 변경 없이 기준 파일로 포함했다.

## 포인터 워크플로 사용 순서

RGBA Roto Master와 Pointer Matte Pack은 첫 프레임에 찍은 포인트로 추적을 시작한다.

1. 영상을 넣고 한 번 실행한다. Points Editor 배경에 첫 프레임이 표시된다.
2. Shift+Click으로 포함 포인트, Shift+Right Click으로 제외 포인트를 찍는다.
3. 다시 실행한다. 시드 프레임은 frame 0으로 고정한다. SAM3_VideoTrack의 initial_mask가 첫 프레임에 적용되기 때문이다.

## 이번 구성에서 바뀐 점

**RGBA Roto Master**
- Reroute 11개, Primitive 2개, 첫 프레임 PreviewImage를 제거하고 메인 서브그래프로 묶었다.
- KJNodes `GetImageSizeAndCount`를 core `GetImageSize`로 교체했다.
- 05 ProRes 출력의 `profile`을 `4444`로 지정했다. VHS ProRes 기본값 `hq`는 알파 채널을 기록하지 않아서 RGBA가 불투명하게 저장되던 문제를 고쳤다.

**Pointer Matte Pack**
- Reroute 버스와 PreviewAnimation 3개를 제거했다. 같은 결과를 각 SaveVideo가 미리보기로 보여준다.
- SAM3_TrackPreview는 서브그래프 안에 bypass 상태로 남겼다. 필요할 때 Ctrl+B로 켠다.
- BBOX, 피사체만, 배경만, 화이트 마스크 영상에 원본 오디오를 넣었다. 매트 영상은 무음이다.
- 텍스트 프롬프트 노드는 서브그래프 안에 남겨 두었지만 연결하지 않았다. 기본 동작은 포인터 전용이다.

**SAM3D Body + MoGe**
- 레거시 PrimitiveNode(렌더 폭, 포즈 오버레이 강도)를 서브그래프 위젯으로 바꿨다.
- Video Slice의 시작 시간과 길이를 위젯으로 뺐다. `duration = 0`은 전체 길이다 (Video Slice 툴팁 기준).
- BuildPoseFile의 fps를 원본 영상 fps에 연결했다. 기존에는 24로 고정되어 있어 GLB 애니메이션 타이밍이 원본과 어긋날 수 있었다.
- 포즈 GLB 2종을 SaveGLB로 `output/3d/`에 이름 붙여 저장한다. Preview3D 뷰어는 그대로 유지했다.

## 필요 모델·노드

| 항목 | 위치 / 출처 |
|---|---|
| `sam3.1_multiplex_fp16.safetensors` | `models/checkpoints/` — Comfy-Org/sam3.1 |
| `sam_3d_body_dinov3_bf16.safetensors` | `models/detection/` — Comfy-Org/sam-3d-body |
| `moge_2_vitl_normal_fp16.safetensors` | `models/geometry_estimation/` — Comfy-Org/MoGe |
| `rt_detr_v4-x-hgnet_fp32.safetensors` | `models/diffusion_models/` — Comfy-Org/SDPose |
| ComfyUI core | 서브그래프 지원 프런트엔드, 네이티브 SAM3 / SAM3D Body / MoGe 노드 |
| 커스텀 노드 | KJNodes (Points Editor), VideoHelperSuite (Roto Master), maskvidexperiments (Pointer Matte Pack) |

## 검증 범위

- 정적 검증을 마쳤다: 두 그래프 레벨의 링크·슬롯 양방향 참조, 타입 호환, 전역 ID 중복, 서브그래프 입력과 위젯 값 개수.
- `@comfyorg/litegraph` 0.17.2로 로드해 서브그래프 위젯이 올바른 값으로 생성되는지 확인했다. 같은 엔진의 `ExecutableNodeDTO` 평탄화로 모든 내부 입력이 실제 상위 노드나 서브그래프 위젯 값으로 해석되는지도 확인했다. 결과는 4개 파일 모두 문제 0건이다.
- 원본과 평탄화 결과를 비교했다. 차이는 위에 적은 의도된 변경뿐이다.
- 실제 ComfyUI에서 SAM/비디오 추론은 실행하지 않았다. 처음 실행할 때 첫 프레임, 중간 프레임, 마지막 프레임의 매트 경계와 프레임 수·FPS 일치를 확인한다.
