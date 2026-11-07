# Frozen Look 파이프라인 (니쥬 · 01_컷별 프레임)

완성본 3장(테이블 투샷 / 웨이터 라운지 / 복도)의 **떼깔**로 나머지 컷별 프레임을 일괄 변환한다.
ComfyUI + **Qwen-Image-Edit-2511**로 서리·눈·고드름을 얹고, `grade_match.py`로 레퍼런스 톤에 색을 고정한다.

```
원본 프레임 ─▶ ~1MP 축소 ─▶ Qwen-Image-Edit-2511 (원본 + 룩 레퍼런스 + 프롬프트)
            ─▶ 원본 해상도 복원 ─▶ 레퍼런스 룩 그레이드 ─▶ 프레임_frozen/  + 컨택트 시트
```

원본 폴더는 읽기만 한다. 결과는 항상 별도 폴더(기본 `<입력>_frozen`)에 저장된다.

## 구성

| 파일 | 역할 |
|---|---|
| `batch_freeze.py` | 폴더 일괄 처리 (ComfyUI HTTP API), 컷당 시드 후보 N장, 로그·컨택트 시트 |
| `grade_match.py` | 레퍼런스 Lab 통계로 톤커브(블랙 리프트·저대비) + 색 캐스트·채도 매칭 |
| `prompts.json` | 프롬프트 원본 (기본·서리·룩·샷 타입별·네거티브). 수정은 여기서 |
| `workflows/qwen2511_frozen_edit_api.json` | ComfyUI API 포맷 워크플로 (UI에 드래그해 수동 테스트 가능) |
| `shots.example.csv` | 컷별 설정 예시 |
| `reference/` | 완성본 3장을 넣는 곳 (git 제외) |

## 1. 모델 설치 (ComfyUI)

ComfyUI 공식 Qwen-Image-Edit-2511 템플릿과 같은 파일이다.

| 폴더 | 파일 |
|---|---|
| `models/diffusion_models` | `qwen_image_edit_2511_bf16.safetensors` (VRAM 부족 시 fp8 버전 + `--unet`로 지정) |
| `models/text_encoders` | `qwen_2.5_vl_7b_fp8_scaled.safetensors` |
| `models/vae` | `qwen_image_vae.safetensors` |
| `models/loras` (선택) | Qwen-Image-Edit-2511 Lightning 4-step LoRA — 빠른 시안용 |
| `models/upscale_models` (선택) | 4x-UltraSharp 등 — 4K 원본일 때 디테일 보강 |

## 2. 실행 (Windows, ComfyUI 포터블 기준)

ComfyUI를 먼저 켠 뒤(`http://127.0.0.1:8188`), 이 폴더에서 ComfyUI의 파이썬으로 실행한다.

```bat
set PY=C:\ComfyUI_windows_portable\python_embeded\python.exe
set IN=C:\Users\<사용자>\Desktop\프로젝트\니쥬\소스_2\01_컷별\프레임
```

① 컷 목록 CSV 만들기 → 엑셀로 열어 `shot`/`ref`/`skip` 채우기 (완성된 3장은 `skip=1`)

```bat
%PY% batch_freeze.py --in "%IN%" --init-shots shots.csv
```

② 계획 확인 (ComfyUI 호출 없음)

```bat
%PY% batch_freeze.py --in "%IN%" --shots shots.csv --dry-run
```

③ 빠른 시안 (Lightning LoRA, 컷당 2후보)

```bat
%PY% batch_freeze.py --in "%IN%" --shots shots.csv --lora <Lightning LoRA 파일명> --steps 4 --cfg 1
```

④ 본 작업 (품질 우선)

```bat
%PY% batch_freeze.py --in "%IN%" --shots shots.csv --steps 40 --cfg 4 --variants 3 --force
```

### shots.csv 열

| 열 | 값 |
|---|---|
| `shot` | `cu` 클로즈업 · `ms` 미디엄 · `ws` 와이드(공간 전체 결빙) · `walk` 복도/걷기 |
| `ref` | `1`·`2`·`3` (reference 폴더 정렬 순) · 파일 경로 · `none`(텍스트만) |
| `skip` | `1`이면 건너뜀 |
| `seed` / `variants` | 컷별 시드 고정 / 후보 수 |
| `extra` | 이 컷에만 붙일 영어 프롬프트 (예: `Keep the silver tray level.`) |

## 3. 출력과 검수

```
프레임_frozen/
  C002_frz_v01.png ...   ← 그레이드 적용 최종 후보 (원본 해상도)
  raw/                   ← 그레이드 전 AI 결과
  log.jsonl              ← 컷별 프롬프트·시드·설정 기록 (재현용)
  _contact_sheet.jpg     ← 왼쪽 원본 | 오른쪽 후보들
```

컨택트 시트로 먼저 고르고, 아래 항목은 원본 해상도로 확인한다.

- 얼굴·시선·표정이 원본과 같은가 (다른 사람으로 바뀌면 시드 교체 또는 `--no-ref`)
- 눈동자가 얼지 않았는가, 손가락 수·소품 형태가 유지되는가
- 서리가 **파랗지 않고** 중성 화이트인가, 전체가 크림/아이보리 톤인가
- 레퍼런스의 인물·소품이 섞여 들어오지 않았는가 (섞이면 그 컷만 `ref=none`)
- 프레이밍이 원본과 일치하는가 (AE에서 원본 위에 Difference로 겹쳐 확인)

## 레퍼런스 룩 (측정값)

| | 블랙(p1) | 미드(p50) | 하이(p99) | 평균 채도 | 특징 |
|---|---|---|---|---|---|
| ref 1 테이블 | 0.06 | 0.49 | 0.85 | 0.14 | 크림 벽, 섀도 약한 마젠타 |
| ref 2 웨이터 | 0.26 | 0.64 | 0.95 | 0.12 | 짙은 헤이즈, 블랙 크게 들림 |
| ref 3 복도 | 0.08 | 0.51 | 0.97 | 0.27 | 따뜻한 베이지·골드 |

공통: 저채도·저대비, 밀키한 블랙, 크림/아이보리 하이라이트, 서리는 중성 화이트, 얕은 심도와 따뜻한 보케.
`grade_match`는 컷이 쓴 레퍼런스 70% + 3장 평균 30%를 타깃으로 잡는다. 컷 성격은 살리면서 시퀀스 톤을 통일하기 위해서다.

## 그레이드만 따로 돌리기

다른 툴(H3, Nano Banana 등)로 만든 결과도 같은 떼깔로 맞출 수 있다.

```bat
%PY% grade_match.py --in 결과폴더 --out 결과폴더_graded --ref reference --strength 0.6 --report
```

## 사실감·화질 올리기 (모델 무관)

1. **원본에 인물 영역만 합성**: 효과가 가장 크다. 편집 모델은 손대지 않은 배경까지 뭉개므로, ComfyUI 기본 블루프린트 `Image Segmentation (SAM3)`에 `text=person`을 넣어 인물 마스크를 뽑는다. 원본 위에 AI 결과를 그 마스크(약간 확장 + 페더)로만 얹으면 건축·조명은 원본 4K 그대로 남는다. AE에서는 원본 위에 결과 레이어를 올리고 마스크를 Track Matte로 쓴다.
2. **Turbo·int8은 시안용**: 8 step 증류 모델과 int8 양자화는 피부·눈 질감을 매끈하게 만든다. 본 작업은 bf16/fp8 가중치와 비증류 설정(steps 30~40, CFG 3~4)을 쓰거나, 편집 해상도가 큰 모델(H3: 약 8.5MP)을 쓴다.
3. **디테일 패스**: ComfyUI 기본 블루프린트 `Image Upscale (Z-image-Turbo)`로 저강도(denoise 0.2~0.33) 리파인을 하면 서리 결정과 피부 질감이 살아난다. 0.4를 넘기면 얼굴이 바뀐다.
4. **그레인·색 통일**: `grade_match.py --grain 0.008~0.015`로 원본 노이즈와 레퍼런스 떼깔에 맞춘다.

H3 전용 프롬프트와 연결 체크리스트는 `PROMPTS_H3.md`에 있다.

## 인물만 얼리는 컷 (공간은 유지)

로툰다 와이드처럼 주변 인물만 얼려야 하는 컷은 `ws` 대신 `ms`로 두고 `extra`에 아래 문장을 넣는다.

```
Freeze only the people and what they wear or hold. Do not add snow or ice to the walls, dome, ceiling, floor or furniture. Make the frost clearly visible even on small, distant figures.
```
