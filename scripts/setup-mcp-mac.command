#!/bin/bash
cd "$(dirname "$0")"
if ! command -v node >/dev/null 2>&1; then
  echo "[X] Node.js가 없습니다. https://nodejs.org 에서 24 이상 LTS를 설치한 뒤 다시 실행하세요."
  open https://nodejs.org
  read -r -p "Enter를 누르면 닫힙니다."
  exit 1
fi
node ./setup-mcp.mjs
read -r -p "Enter를 누르면 닫힙니다."
