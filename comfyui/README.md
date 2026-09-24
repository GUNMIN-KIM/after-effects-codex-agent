# ComfyUI Wan 워크플로 — Creator UI 디벨롭

Wan Animate 2에서 쓰던 **MAIN CONTROL 한 패널 + Source/Custom 모드 + 원본 길이·FPS·오디오 자동 유지** 방식을 Wan VACE 워크플로 두 개에도 똑같이 적용하고, Animate 2는 버그를 고친 revision 4로 올렸다. 기준 환경은 **ComfyUI v0.31.1**이며 core 노드만 쓴다.

| 파일 | 원본 | 용도 |
|---|---|---|
| `workflows/WAN_Animate2_CreatorUI.json` | `source/WAN_Animate2_rev3_original.json` | Reference Image + Driving Video → 모션 전이 (rev 4) |
| `workflows/WAN_VACE_1.3B_14B_CreatorUI.json` | `source/WAN_VACE_1.3B_14B_original.json` | 마스크 영역 배경 확장·교체, 1.3B/14B 선택 |
| `workflows/WAN_VACE_Inpaint_2x_PixelLock_CreatorUI.json` | `source/WAN_VACE_Inpaint_original.json` | 마스크 영역 인페인트 + 원본×2 출력 + Pixel Lock |

LoadVideo / LoadImage 파일명, 프롬프트, 시드, LoRA 강도 등 원래 값은 그대로 유지했다.

## 무엇이 바뀌었나

### Wan Animate 2 (rev 3 → 4)

- **출력 길이 버그 수정.** Wan은 chunk마다 4k+1 프레임만 디코드하는데 chunk 길이가 4k+1이 아니었다. 그래서 100f 소스는 97f, 170f 소스는 169f, 50f 소스는 49f로 짧게 나왔고, chunk 3은 포즈가 1프레임 밀렸다. 이제 모든 chunk 길이를 4k+1로 올림하고 F도 4k+1로 자동 정렬해서 소스 길이 그대로, 포즈 순서도 프레임 단위로 정확하게 나온다.
- **홀수 해상도 크래시 수정.** Custom Width/Height나 Keep Aspect 결과가 홀수이면 생성이 다 끝난 뒤 SaveVideo(H.264)에서 크래시가 났다. 이제 출력 크기를 항상 짝수로 맞춘다.
- **01 MODEL · Distilled Model 추가.** 증류 모델 파일을 직접 고를 수 있다. 증류 토글은 01 MODEL 맨 위로 옮겼다.
- **08 FILES 추가.** 숨겨진 Text Encoder / CLIP Vision / VAE 로더가 `Comfy-Org__Wan-Animate-2__…` 파일명에 고정돼 있어서, 노트대로 받은 파일로는 실행이 안 됐다. 이제 패널에서 고를 수 있다.
- **모델 노트.** 증류 모델(기본값) 다운로드 링크를 추가하고 chunk 수식 설명을 갱신했다.
- **비교 노드.** 입력 이름을 Result (left) / Driving (right)로 바꿨고, 출력 파일명은 `video/Wan_Animate2*`로 정리했다.

### Wan VACE 두 파일 → Creator UI

- **MAIN CONTROL 한 패널.** 01 MODEL · 02 PROMPT · 03 VIDEO · 04 RESOLUTION · 05 FPS · 06 MASK · 07 VACE · 08 SEED · 09 FILES.
- **Control 영상 채움색.** 마스크 영역을 흰색 대신 **Gray 0.5**로 채운다. VACE 학습 규칙이 `MASK_COLOR = 128`이다 (ali-vilab/VACE `annotators/inpainting.py`).
- **Canvas.** 원본 비율을 유지하고 16px로 정렬하며, 480p 또는 720p 면적 중 토글로 고른다. 이전 1.3B/14B 파일은 1280×720으로 고정돼 있었다.
- **길이.** 4k+1 길이로 생성한 뒤 target 프레임 수로 정확히 자른다.
- **마스크 처리.**
  - 길이를 소스에 맞춘다. 마스크가 짧으면 마지막 프레임을 유지한다.
  - Canvas 크기로 리사이즈하고 red 채널을 쓴다 (흰색 마스크도 인식).
  - Invert, 0.5 이진화, Expand, 8px Block Align 옵션을 제공한다.
  - 8px Block Align은 커스텀 노드였던 `BlockifyMask`를 core 노드로 대체한 것이다.
- **출력 크기.** Source × Scale(1.3B/14B는 1.0, Inpaint는 2.0) 또는 Custom이며, 항상 짝수로 맞춘다.
- **Pixel Lock.** 출력 해상도에서 마스크 밖은 원본 픽셀을 그대로 쓴다.
- **FPS·오디오·Custom 모드.** 소스 FPS와 오디오를 유지하고 Length / FPS Custom 모드를 제공한다. 이전 1.3B/14B 파일은 오디오가 없었고 출력이 1920×1080으로 고정돼 있었다.
- **선택 노드.** Control/Mask Preview와 결과/원본 비교 출력은 지워도 된다.
- **프롬프트 (1.3B/14B).** 긍정 프롬프트 안에 있던 `NEGATIVE PROMPT (STRICT)` 블록을 Negative Prompt 칸으로 옮겼다.
- **모델 노트.** 클릭 다운로드 링크를 넣었고, 로더에는 `properties.models` 메타데이터를 달았다.

## 검증 방법과 한계 (dry-run)

`dryrun/` 테스트 벤치는 **실제 ComfyUI v0.31.1 서버와 실제 프론트엔드**를 그대로 쓴다. 대신 모델 연산(로더, 샘플러, VAE, 텍스트/비전 인코더)만 모양이 같은 stub으로 바꾼다.

1. headless Chromium으로 워크플로를 프론트엔드에 로드한 뒤 `app.graphToPrompt()`로 사용자 UI가 보내는 것과 똑같은 API 프롬프트를 만든다.
2. 서버가 그 프롬프트를 검증하고 실행한다. 스위치의 lazy 평가, 수식, 리사이즈, 합성, CreateVideo, SaveVideo는 모두 실제 코드다.
3. 합성 입력 영상은 매 프레임 색으로 프레임 번호를 새겨 둔다. 출력 mp4를 디코드해서 프레임 수, FPS, 해상도, 오디오, 프레임별 번호 순서, 마스크 영역 Gray, 마스크 밖 원본 일치도(≤ 1.5/255)를 확인한다.

결과는 다음과 같다.

- Animate2 11개, VACE 14개 케이스 전부 통과했다.
- 프론트엔드 1.48.7, 1.50.6, 1.54.7에서 모두 동일하게 동작했다.
- **GPU 실렌더는 하지 않았다.** 생성 화질과 VRAM 사용량은 실제 환경에서 확인해야 한다.

```bash
cd comfyui/dryrun
bash setup.sh          # 최초 1회: ComfyUI v0.31.1 + stub + 합성 입력 영상
bash setup.sh serve &  # 서버 실행
python test_anim.py && python test_vace.py
```

## 다시 빌드

```bash
cd comfyui/build
python patch_animate2.py   # source/ Animate2 rev3 → workflows/ rev4
python build_vace.py       # vace_configs.py 기본값으로 VACE 두 파일 생성 (UUID 고정 → 재빌드해도 동일)
```
