# H3 (P-H3-Image) 편집 프롬프트

노드 동작은 ComfyUI 소스 `comfy_extras/nodes_minimax_h3.py`로 확인했다.

## 권장: 공식 템플릿 `image_p_h3_image_edit` (실사용에서 결과 양호)

`06_H3_P-H3-Image` 커스텀 파일보다 결과가 좋았던 이유는 아래 차이 때문이다. 이 설정은 그대로 유지한다.

| 항목 | 공식 템플릿 (좋음) | 06 커스텀 |
|---|---|---|
| 편집 해상도 | `Upsampler vision size`(ImageScaleToTotalPixels) **바이패스** → 원본 그대로 (3840×2160 → 3840×2160) | `edit_mp` 4 → 2720×1536 후 확대 |
| 편집 입력 | LoadImage가 항상 image_1에 연결됨 | 편집 모드 OFF·① 바이패스면 텍스트→이미지(2912×2912)로 돌아감 |
| 샘플러 | `er_sde` (확률적, 질감 자연스러움) | `euler` |
| 모델 | `minimax_h3_fl2va_pruned_int8_convrot` + `p-h3-image_lora_bf16` (strength 1) | `p-h3-image_int8_convrot` 단일 파일 |
| 업샘플러 | `w4a8`, TextGenerateV2, thinking ON, 1536 | `bf16`, 편집용 커스텀 템플릿, 3072 |

- 시그마(8 steps)와 `ModelSamplingMiniMaxH3` 1.0/1.0은 두 파일이 같다.
- `Upsampler vision size`를 켜면(0.95MP) 결과도 약 1MP로 작아진다. 4K로 받으려면 바이패스를 유지한다.
- 후보는 `RandomNoise` 시드만 바꿔서 뽑는다 (공식 파일은 `fixed`).
- 프롬프트는 `Text (Prompt)` 노드에 넣는다. 아래 상세 프롬프트를 그대로 넣어도 업샘플러가 정리한다. 업샘플 결과는 `Upsampled prompt` 노드에서 확인한다.

## 06 커스텀 파일을 쓸 때

### 결과가 정사각 2912×2912 + 다른 사람으로 나오면

편집이 아니라 **텍스트→이미지**로 돌았다는 뜻이다. 편집 모드가 꺼져 있으면 image_1 자리에 빈 이미지가 들어가고, 비율 표의 1:1 값(2912×2912)으로 새 그림을 만든다.

| 순서 | 할 일 |
|---|---|
| 1 | `① 편집할 이미지` LoadImage 바이패스 해제 (선택 후 **Ctrl+B**, 보라색 해제) → 원본 프레임 넣기 |
| 2 | 메인 노드 **이미지 편집 모드 = ON** |
| 3 | 레퍼런스를 쓸 때만: `② 참조 이미지 1` 바이패스 해제 + 완성본 1장 넣기 + **참조 이미지 수 = 1** |
| 4 | 실행 후 `모델에 들어간 프롬프트`(PreviewAny)에서 업샘플러가 "인물만" 조건을 지웠는지 확인 |
| 5 | 결과 크기가 원본 비율(16:9)인지 확인. 편집 4MP면 3840×2160 원본이 2720×1536으로 나온다 |

요청 칸에는 `Edit <Picture 1>.`를 쓰지 않는다. 업샘플러 템플릿과 컨디셔닝 노드가 앞에 자동으로 붙인다.

## 1) 인물만 얼리기 (공간 유지) · 업샘플러 ON용 (짧게)

```
Freeze only the people in <Picture 1>: snow-caked frozen hair, ice crystals on their faces, eyebrows and eyelashes, snow on their shoulders and collars, frosted coats with short clear icicles hanging from hems and sleeves. Keep every face, pose, position and outfit, and keep the building, dome, floor, furniture, Christmas trees, lighting and framing unchanged. No snow or ice on the building or floor, no new people. Photorealistic real practical frost, warm ivory tones.
```

## 2) 인물만 얼리기 · 업샘플러 OFF용 (상세)

업샘플러가 조건을 빼먹거나 장면을 바꿀 때 `프롬프트 업샘플러 사용 = OFF`로 두고 이걸 쓴다.

```
Keep <Picture 1> exactly as it is: same camera, framing, rotunda architecture, glass dome, columns, lights, Christmas trees, furniture and floor, and every person's face, pose, position, size and clothing. Only freeze the people. Their hair is caked with white snow and frost clumps, fine ice crystals dust their faces, eyebrows and eyelashes, fresh snow sits on their shoulders and coat collars, hoarfrost covers their coats and scarves, and short clear icicles hang from coat hems, sleeves and bags. Eyes stay natural. Do not add snow or ice to the building, floor or furniture, do not add or remove people, and do not change the framing. Real photographic frost with crisp ice crystals and translucent icicles catching the warm light, matching the photo's lens blur, noise and warm ivory color.
```

## 3) 인물 + 소품까지 얼리기 (완성본 3장과 같은 범위)

```
Keep the same camera, framing, room, lighting, and every person's face, expression, pose and clothing in <Picture 1>. Freeze the people and the objects they touch: hair caked with white snow and frost clumps, ice crystals on skin, eyebrows and eyelashes, snow piled on shoulders and lapels, hoarfrost on fabric, clear glassy icicles hanging from jacket hems, cuffs, scarves, trays, cups and table edges, and cups and lamps encased in white frost. Eyes stay clear and alive. Real practical frost, not CGI. Warm ivory-cream palette, frost neutral white not blue, soft low contrast, lifted milky blacks, shallow depth of field.
```

## 레퍼런스(② = `<Picture 2>`)를 쓸 때 끝에 추가

```
Match the frost texture, icicle style and warm ivory color of <Picture 2>, but copy no people, objects or layout from <Picture 2>.
```

## 보조 문장

- 멀리 있는 작은 인물에 서리가 약할 때: `Make the frost clearly visible even on small, distant figures.`
- 특정 인물은 얼리지 않을 때: `Except the woman in the long black coat on the left, who stays completely normal and unfrozen.`

## 화질

- `edit_mp` 기본값은 4(공식 편집 레시피)다. 최종본은 8로 올리면 원본 4K에 가깝게(3840×2176) 나온다. VRAM과 시간이 더 든다.
- 배경까지 미세하게 뭉개지므로, 최종본은 SAM3 인물 마스크로 원본 위에 인물 영역만 합성한다 (README 참고).
