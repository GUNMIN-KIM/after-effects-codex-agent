# GEMINI NEON

쌍둥이 비행선 **카스토르(시안)**와 **폴룩스(마젠타)**를 빛줄기로 묶고, 두 기체의 간격을 조절해 네온 게이트를 통과하는 9:16 세로형 3D 게임이다. 처음부터 영상 소스로 쓰도록 만들었다. 녹화하면 HUD 없이 1080×1920 화면만 저장되고, 프레임이 빠지지 않는 오프라인 렌더러도 함께 들어 있다.

- 엔진: Three.js r170(WebGL2). 빌드 단계 없이 HTML 한 파일로 실행된다.
- 모델·텍스처·셰이더는 외부 에셋 없이 전부 코드로 생성한다(프로시저럴).
- Gemini 같은 외부 생성 모델은 쓰지 않았다.

## 실행

| 방법 | 설명 |
|---|---|
| `index.html` 더블클릭 | Chrome·Edge 권장. three.js와 폰트를 CDN에서 받으므로 인터넷 연결이 필요하다. |
| 로컬 서버 | `npx serve .` 후 브라우저로 접속(모바일 테스트용) |
| claude.ai 아티팩트 | `gemini-neon.html`이 아티팩트 원본이다(문서 골격이 없는 형식). |

`gemini-neon.html`을 수정한 뒤에는 `node build-standalone.mjs`로 `index.html`을 다시 만든다.

## 조작

| 입력 | 동작 |
|---|---|
| 드래그 / 마우스 이동 | 손가락 위치가 오른쪽 기체(폴룩스) 위치가 되고, 왼쪽 기체는 대칭으로 따라온다 |
| `←` `→` 또는 `A` `D` | 모으기 / 벌리기 |
| `Space` | 시작·재시작 |
| `P` / `Esc` | 일시정지 (필름 모드에서 `Esc`는 메인으로) |
| `F` | 필름 모드: 자동 주행 + 카메라 연출, HUD 숨김 |
| `C` | 카메라 앵글 순환: 추적 → 로우 → 사이드 → 탑뷰 → 프론트 → 오빗 |
| `T` | 슬로우 모션 0.35× |
| `H` | HUD 표시 |
| `R` | 녹화 시작·정지 |
| `K` | PNG 스크린샷 |
| `M` | 사운드 |

**규칙**: 도로에 그려진 금색 가이드를 따라가면 다음 장애물을 통과할 수 있다.
- 트윈 게이트: 두 구멍의 위치에 간격을 맞춘다.
- 레이저 펜스: 레이저 안쪽으로 모인다.
- 모노리스: 바깥으로 벌린다.
- 에너지 코어를 모으면 배율(×)이 오르고, 금색 **트윈 스타**를 잡으면 5초 동안 OVERDRIVE(무적·가속) 상태가 된다.
- 실드는 3개다.

## 영상 제작 워크플로

### 1. 실시간 녹화 (빠름)
1. `필름 모드`를 켠다. 자동 주행과 카메라 연출이 시작되고 HUD가 사라진다.
2. 오른쪽 레일의 **녹화** 버튼을 누른다. 녹화 중에는 내부 해상도가 1080×1920으로 고정되고 게임 음악도 함께 녹음된다.
3. Chrome·Edge에서는 MP4로 저장된다. 다른 브라우저에서 WebM으로 저장되면 After Effects에 넣기 전에 MP4로 변환한다.

```bash
ffmpeg -i gemini-neon.webm -c:v libx264 -crf 14 -pix_fmt yuv420p -r 60 gemini-neon.mp4
```

브라우저 녹화는 가변 프레임레이트다. 기기 성능에 따라 프레임이 빠질 수 있으므로 최종 소스로는 아래 오프라인 렌더를 권장한다.

### 2. 프레임 정확 렌더 (최종 소스용)
`render.mjs`는 게임을 고정 시간 간격으로 한 프레임씩 진행시키며 1080×1920 PNG를 저장한다. 결과물은 고정 프레임레이트이며 프레임 누락이 없다.

```bash
npm install
```

```bash
npx playwright install chromium
```

```bash
npm run render:trailer
```

```bash
node render.mjs --seconds 20 --fps 60 --png --out out/frames
```

- `--shots "low:3,chase:4,side:3,top:3,front:2"`: 카메라 하드컷 타임라인. 생략하면 필름 모드의 자동 연출을 쓴다.
- `--png`: PNG 시퀀스로 저장한다. AE에서 이미지 시퀀스로 가져온 뒤 Interpret Footage에서 프레임레이트를 맞춘다.
- `--headed`: GPU를 사용한다(헤드리스 소프트웨어 렌더보다 훨씬 빠르다).
- 오프라인 렌더에는 오디오가 없다. 음악은 실시간 녹화본에서 가져오거나 AE에서 따로 얹는다.

### 3. After Effects
- 컴포지션 1080×1920, 소스와 같은 프레임레이트(60 또는 30)로 만든다.
- 클립에는 HUD가 없다. 타이틀·자막·점수 그래픽은 AE에서 얹는다.
- 원본 `.aep` 보호, 레이어 검수, 렌더 QC는 이 저장소의 `AGENTS.md`, `SKILL.md`, `references/qc-render.md` 규칙을 따른다.

## 기술 구성

| 영역 | 구현 |
|---|---|
| 모델링 | 슈퍼엘립스 단면을 로프트한 동체(72×56 링), 베벨 압출 날개·꼬리날개, 선반(Lathe) 엔진 나셀, 튜브 네온 트림, 이리데선스 캐노피 |
| 텍스처 | 캔버스로 베이크: 투톤 펄 도장·레이싱 스트라이프·패널 라인·리벳·콜사인(알베도), 러프니스/메탈 팩 맵, 높이맵을 소벨 필터로 변환한 노멀맵, 발광맵 |
| 머티리얼 | MeshPhysical(클리어코트, 이방성 금속, 이리데선스 유리), 네온 라이트박스를 PMREM으로 구운 환경맵 |
| 셰이더 | 실시간 반사 + 빗물 왜곡이 들어간 젖은 아스팔트, 인스턴싱 절차적 빌딩(창문·층띠·네온 엣지), 쌍성 태양과 플라스마 브리지·성운·별 하늘, 헥스 홀로 게이트(SDF), 에너지 테더, 엔진 화염, 홀로그램 간판, GPU 빗줄기 |
| 이펙트 | 리본 트레일, GPU 파티클, 인스턴스 파편, 슬로우모션 피격 연출 |
| 포스트 | HDR 렌더(MSAA 4×) → Unreal Bloom → 아나모픽 스트릭·색수차·비네트·그레인 → ACES 톤매핑 |
| 사운드 | Web Audio 생성형 신스웨이브(킥·스네어·하이햇·베이스·패드·아르페지오) + 효과음, 녹화 트랙으로도 라우팅 |

실시간 WebGL이므로 언리얼 엔진 5의 Lumen·Nanite나 블렌더 Cycles 같은 오프라인 패스 트레이싱과 같은 수준은 아니다. 대신 같은 제작 방식(프로시저럴 모델링, PBR 텍스처 세트, HDR 포스트 프로세싱)을 브라우저 안에서 구현했다.

## 영상 생성 프롬프트 (선택)

렌더한 클립을 ComfyUI 영상 투 영상(깊이·라인아트 ControlNet + 비디오 확산 모델) 파이프라인에 넣을 때 쓸 수 있는 예시다.

```text
Positive: vertical 9:16 cinematic shot, twin pearl-white hover jets racing through a rain-soaked neon megacity canyon at night, one trailing cyan light and one magenta, a crackling energy tether between them, wet asphalt mirror reflections, binary twin suns joined by a plasma bridge on the horizon, holographic hangul signage, volumetric haze, anamorphic lens flares, ultra detailed hard-surface panel lines, 35mm film grain
Negative: daylight, flat lighting, cartoon, low detail, warped hulls, extra wings, text artifacts, watermark
```

권장 흐름: `render.mjs --png`로 소스를 만든 뒤 VideoHelperSuite의 Load Video(또는 이미지 시퀀스 로드) → 깊이 추정 → ControlNet → 샘플러 → Video Combine 순서로 연결한다. 디노이즈 강도는 0.35–0.5에서 시작하면 형태가 유지된다.

## 파일

| 파일 | 역할 |
|---|---|
| `gemini-neon.html` | 게임 원본(아티팩트 형식) |
| `index.html` | 독립 실행용 완성 페이지(`build-standalone.mjs`가 생성) |
| `build-standalone.mjs` | 원본을 `index.html`로 감싸는 스크립트 |
| `render.mjs` | 프레임 정확 1080×1920 렌더러(Playwright + ffmpeg) |
| `package.json` | 렌더러 의존성(Playwright)과 npm 스크립트 |
