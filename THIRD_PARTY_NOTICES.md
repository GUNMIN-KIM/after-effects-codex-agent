# Third-Party Notices

이 저장소는 Adobe After Effects와 `mcp-aftereffects`를 함께 사용할 때의 작업 지침과 템플릿을 제공한다. 해당 MCP의 소스 코드나 패키지를 이 저장소에 복제하지 않는다. Adobe, After Effects, Codex, Seedance 및 관련 명칭·상표는 각 권리자에게 귀속된다.

해당 MCP의 현재 설치·라이선스·버전·요구사항은 해당 프로젝트의 공식 저장소와 패키지 문서를 확인한다. 이 저장소의 문서는 MCP 서버 또는 Adobe 제품을 재배포하지 않으며, 사용자가 적법하게 설치한 실행 환경을 전제로 한다.

## ComfyUI 워크플로 팩 (`comfyui/`)

`comfyui/workflows/`의 JSON은 ComfyUI 그래프 정의입니다. 모델 가중치, ComfyUI, 커스텀 노드의 소스 코드는 포함하지 않습니다. 모델은 각 노드의 다운로드 정보가 가리키는 원 배포처에서 사용자가 직접 받으며, **각 모델의 라이선스(상업 이용 가능 여부 포함)는 해당 모델 카드를 따릅니다.** 예를 들어 Qwen-Image 2.1은 기존 팩 노트에 Qwen Research License(비상업)로 적혀 있습니다. 실제 조건은 모델 카드에서 다시 확인하세요.

| 출처 | 포함 범위 | 라이선스 |
|---|---|---|
| Comfy-Org/workflow_templates (`comfyui-workflow-templates-json` 0.1.129) | `H3/06`~`09`, `이미지편집/p-h3-image…`, `로토/Qwen2.1_배경제거…`, `유료API/H3Max_{Reframe,Recast,카메라컨트롤}`의 그래프 구조 | MIT |
| Lightricks/ComfyUI-LTXVideo `example_workflows/2.5` (220e1d4) | `LTX2.5/04`, `LTX2.5/05`, `업스케일/ltx/` 2종, `인페인팅/LTX25_인페인팅_HDR_EXR시퀀스`의 그래프 구조 | LTX-2 Community License. 원문: `comfyui/licenses/LTX-2-Community-License.txt` |
| ComfyUI (Comfy-Org/ComfyUI), ComfyUI-KJNodes, ComfyUI-VideoHelperSuite, comfyui_controlnet_aux, ComfyUI_Nvidia_VFX_Nodes | 노드 이름·입력 정의 참조 (코드 미포함) | 각 프로젝트 라이선스 |
| 유료 API 노드 (MiniMax H3 Max via Comfy, Bria) | 노드 호출 그래프만 포함 | 각 서비스 이용약관 · Comfy 계정 크레딧 |

MiniMax, H3, Hailuo, Lightricks, LTX, Pika, FastVideo, Pruna, Wan, Qwen, Bria, NVIDIA, RTX 및 관련 명칭·상표는 각 권리자에게 귀속됩니다.
