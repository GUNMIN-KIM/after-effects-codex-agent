# LTX-2.5 프롬프트 가이드 — VFX 편집·IC-LoRA용

이 팩의 LTX-2.5 워크플로에 넣는 프롬프트를 워크플로별로 정리했습니다. 프롬프트 본문은 **영어**로 씁니다. EditAnything 워크플로는 한국어 요청을 받아 내부 LLM이 영어로 바꿉니다. 근거는 다음 세 가지입니다.

- 각 워크플로 노트
- EditAnything 워크플로에 들어 있는 프롬프트 변환 지침 (학습 캡션 6829개 통계)
- Lightricks `example_workflows/2.5` README

---

## 1. 다섯 줄 요약

1. **편집 IC-LoRA는 "바뀌는 것"만 씁니다.** 원본에 이미 있는 것을 다시 묘사하면 그 대상이 복제되거나 위치가 흔들립니다.
2. **EditAnything**은 `edit_anything:`로 시작하고, 문장은 `Replace / Add / Remove / Restyle` 네 동사로만 씁니다.
3. **인페인팅·제거는 빈 프롬프트부터** 시작합니다. 필요할 때만 마스크 안에 생길 내용을 짧게 씁니다.
4. **타일 퓨전 업스케일과 2단계 프롬프트에는 룩·스타일만** 씁니다(조명, 팔레트, 필름, 선명도). 사물 이름은 타일마다 찍혀 나옵니다.
5. **AlphaGen과 SDR→HDR은 프롬프트를 쓰지 않습니다.** AlphaGen은 비워 두고, SDR→HDR은 고정 장면 임베딩을 씁니다.

---

## 2. 워크플로별 형식

### 2-1. `LTX2.5/01_EditAnything` — 문장 편집
메인 노드에는 한국어나 영어로 원하는 편집을 적습니다. 내부 LLM(Qwen3-VL-4B)이 영상 프레임을 보고 아래 형식으로 바꿉니다. 직접 쓸 때도 같은 형식을 지킵니다.

```text
edit_anything: Replace <원래 대상 · 색/위치/소유자로 특정> with <새 대상 · 속성 묘사>. <두 번째 편집 문장>.
```

| 동사 | 학습 비율 | 규칙 | 예시 |
|---|---|---|---|
| `Replace … with …` | 50% | 가장 안정적이고 기본입니다. 반드시 ` with `를 넣습니다 | `Replace the gray hoodie worn by the man with a bright red zip-up jacket with white stripes on the sleeves.` |
| `Add a …` | 26% | 한 문장에 물체 하나만 넣고, **화면 속 실제 요소 기준 위치**를 붙입니다 | `Add a large green potted plant with broad leaves to the desk area on the right side of the frame.` |
| `Remove …` | 18% | 누가 들고 있는지·입고 있는지까지 특정합니다 | `Remove the smartphone held in the man's hand.` |
| `Restyle … into … style` | 5% | **영역** 단위로 씁니다(벽·화면·배경). 영상 전체에 쓰지 않습니다 | `Restyle the large blue digital screen behind the man into flat vector style.` |

- 한 문장은 10~20단어로 씁니다(중앙값 15).
- 요청한 편집 수만큼만 문장을 씁니다. 요청하지 않은 하늘·조명 변경은 결함입니다.
- `Make it …`, `Turn it into …`는 학습 데이터에 없으므로 쓰지 않습니다.
- 여러 마리·군중처럼 여러 개가 필요하면 `Add several`이 아니라 기존 영역을 그 무리로 `Replace`합니다.
- 방향·자세는 상태로 적습니다(`facing the same direction she is moving`). `gracefully`, `beautifully` 같은 부사는 쓰지 않습니다.

### 2-2. `LTX2.5/02_Ripple` — 수정한 첫 프레임 전파
바뀔 모습은 이미지가 결정하므로 프롬프트는 전파 지시만 둡니다. 기본값을 그대로 씁니다.

```text
Use the reference video for motion, timing, camera movement, composition, and unchanged scene content, while consistently propagating the visual edit established in the first frame throughout the video.
```

교체 대상을 꼭 밝혀야 할 때만 한 문장을 덧붙입니다: `The red mug on the table is now a blue ceramic teapot.`

### 2-3. `LTX2.5/03_V2V` — 원본을 밑그림으로 룩 재생성
결과 장면 전체를 한 문단으로 씁니다. 순서는 **주 동작 → 인물·사물 외형 → 배경 → 카메라 → 조명·색**입니다. 강도 단계 5에서 시작합니다.

```text
A woman in a long wool coat walks along a rain-soaked night street, neon signs reflecting in the puddles. The camera tracks backward at walking pace. Cold cyan street light mixes with warm shop windows, fine film grain, shallow depth of field.
```

### 2-4. `제거/ltx/LTX2.5_클린플레이트` — 마스크 없이 사람·차량 제거
**비어 있는 장소**를 긍정문으로 묘사합니다. 네거티브에는 남을 수 있는 것(사람·팔다리·그림자·잔상)을 둡니다. 워크플로 기본값이 이 형식입니다.

```text
An empty clean plate of the exact same location: identical background, environment, structures and lighting as the source video, with no people, no humans, no figures, and no body parts such as arms, hands or legs anywhere in the frame. Static photorealistic footage, natural light, high detail.
```

### 2-5. 인페인팅 (`인페인팅/LTX25_…참조첫프레임`, `인페인팅/LTX25_인페인팅_HDR_EXR시퀀스`)
- **제거만 할 때**: 프롬프트를 비웁니다.
- **교체할 때**: 마스크 안에 생길 것만 1~2문장으로 씁니다: `A wooden park bench with green iron armrests stands on the gravel path.`
- 보호 영역까지 장면 전체를 설명하면 사물·인물이 마스크 안에 복제됩니다.

### 2-6. 아웃페인팅 (`아웃페인팅/LTX2.5_…`)
화면 밖으로 **이어질 것**만 씁니다. 레퍼런스를 쓸 때는 `from the reference`를 넣습니다.

```text
The brick alley continues on both sides with the same wet cobblestones, fire escapes and warm window light.
```

### 2-7. `LTX2.5/04_DayToNight_리라이트` (타일 퓨전 · 2단계)
| 단계 | 쓰는 것 | 예시 |
|---|---|---|
| 1단계 (FullHD · IC-LoRA) | 원하는 **변화** | `The same street at night: sodium street lamps glow orange, shop windows are lit from inside, the sky is deep navy, wet asphalt reflects the lights.` |
| 2단계 (타일 퓨전 업스케일) | **룩·스타일만** | `Cinematic night photography, crisp detail, soft halation around light sources, gentle film grain, deep clean blacks.` |

### 2-8. `업스케일/ltx/LTX2.5_디테일리파인_TiledFusion` · `LTX2.5/05_UnionControl`
- **업스케일**: 룩·스타일만 씁니다: `Sharp natural detail, realistic skin texture, clean edges, subtle 35mm film grain.`
- **Union Control (깊이·캐니·포즈)**: 구조는 컨트롤 영상이 정하므로 **재질·조명·인물 외형**을 씁니다: `Photorealistic live-action: a concrete parking garage lit by flickering fluorescent tubes, a man in a black leather jacket walking toward the camera.`

### 2-9. `업스케일/ltx/LTX2.5_SDR→HDR` · `로토/LTX2.5_알파매트_AlphaGen`
- **SDR→HDR**: 자유 프롬프트를 쓰지 않습니다. `ltx-2.5-22b-ic-lora-sdr-to-hdr-scene-emb` 고정 임베딩을 씁니다.
- **AlphaGen**: 프롬프트를 **비워 둡니다**. 텍스트로 대상을 지정할 수 없습니다. 대상 지정이 필요하면 SAM3.1 로토를 씁니다.

### 2-10. `프레임보간/ltx/…영상연장` · `…슬로모션x2`
- **영상연장**: 첫 문장을 `A single continuous shot that seamlessly continues the source clip …`으로 시작하고, 이어지는 동작을 씁니다. 부정문("no cut")은 CFG 1에서 약하게 먹습니다.
- **슬로모션**: 장면을 짧게 묘사하면 사이 프레임이 안정됩니다: `A dancer spins on a wooden stage under a single warm spotlight.`

---

## 3. 공통 규칙 (LTX-2.5)

| 이렇게 | 대신 이렇게 쓰지 말기 |
|---|---|
| 화면 기준 위치: `on the right side of the frame`, `in the lower background` | 인물 기준 좌우(`to her left`)만 쓰기 |
| 상태 묘사: `sitting upright on the desk` | 부사·평가어: `beautifully`, `epic`, `8K`, `masterpiece` |
| 하나의 연속 샷을 현재형 한 문단으로 | 컷 나열, 타임코드 남발(편집 IC-LoRA에서는 무시되거나 흔들림) |
| 바뀌는 것만 (편집 계열) | 원본에 이미 있는 것을 다시 나열 |
| 원하는 모습을 긍정문으로 | 금지어 목록(`no …, no …, no …`) |

- 규격: 프레임 수는 **8k+1**(97·121…)입니다. 해상도는 1단계 32배수, 2단계(×2) 64배수입니다. 24fps가 기본이고, 30fps를 넘는 원본은 조건 fps가 60으로 맞춰집니다.
- 디스틸 1단계 시그마: `1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0` (euler_ancestral)
- 디스틸 2단계 시그마: `0.909375, 0.725, 0.421875, 0.0` (Lightricks 공식. 이번 업데이트에서 0.85 → 0.909375로 교정)
- Lightricks 공식 IC-LoRA·HDR·타일 퓨전 그래프(이번에 추가한 04·05·업스케일·HDR)는 **euler**를 씁니다. 이 팩의 기존 AlphaGen·클린플레이트·아웃페인팅 1단계는 제작 당시 기준인 euler_ancestral을 그대로 둡니다.
- 프롬프트 강화(`TextGenerateLTX2Prompt`)를 켜면 문장이 길어집니다. 재현이 필요하면 끄고 직접 씁니다.

---

## 4. 다른 LLM에게 맡길 때 (복사용 지시문)

```text
You write prompts for LTX-2.5 video editing workflows used in VFX compositing.
Write in English. Describe only what must change; never re-describe content that already exists in the source video.
If the workflow is EditAnything: start with "edit_anything:", then one sentence per requested edit, each starting with Replace (must contain " with "), Add a/an (one object, anchored to a visible element and a frame position), Remove (identify owner/position), or Restyle (a named region, "into <style> style"). 10-20 words per sentence. No "make it", no "turn it into", no adverbs of manner, no unrequested edits.
If the workflow is inpainting/removal: return an empty prompt for pure removal, otherwise 1-2 sentences describing only what appears inside the mask.
If the workflow is a tiled-fusion upscale or a second stage: describe only look and style (lighting, palette, film stock, sharpness, grade), no named objects or people.
Use screen-relative directions (screen-left/right, foreground/background) and positive phrasing.
My edit: <한국어로 원하는 편집 설명>
```
