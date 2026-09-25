@echo off
chcp 65001 >nul
where node >nul 2>nul
if errorlevel 1 (
  echo [X] Node.js가 없습니다. https://nodejs.org 에서 24 이상 LTS를 설치한 뒤 다시 실행하세요.
  start https://nodejs.org
  pause
  exit /b 1
)
node "%~dp0setup-mcp.mjs"
pause
