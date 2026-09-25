// After Effects MCP(@kumoproductions/mcp-aftereffects)를 Claude Desktop과 Claude Code에 등록한다.
// 기존 설정 파일은 덮어쓰기 전에 .bak-<timestamp>로 백업한다.
import { execSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const SERVER_NAME = "aftereffects";
const PACKAGE = "@kumoproductions/mcp-aftereffects";
const isWin = process.platform === "win32";

const major = Number(process.versions.node.split(".")[0]);
if (major < 24) {
  console.error(`[X] Node.js ${process.versions.node} 감지. 24 이상이 필요합니다: https://nodejs.org`);
  process.exit(1);
}
console.log(`[OK] Node.js ${process.versions.node}`);

// 1) Claude Desktop 설정 파일에 병합
const desktopConfig = isWin
  ? path.join(process.env.APPDATA ?? path.join(os.homedir(), "AppData", "Roaming"), "Claude", "claude_desktop_config.json")
  : path.join(os.homedir(), "Library", "Application Support", "Claude", "claude_desktop_config.json");

const entry = isWin
  ? { command: "cmd", args: ["/c", "npx", "-y", PACKAGE] }
  : { command: "npx", args: ["-y", PACKAGE] };

let config = {};
if (fs.existsSync(desktopConfig)) {
  const raw = fs.readFileSync(desktopConfig, "utf8");
  try {
    config = raw.trim() ? JSON.parse(raw) : {};
  } catch {
    console.error(`[X] ${desktopConfig} JSON 파싱 실패. 파일을 수정하지 않고 중단합니다.`);
    process.exit(1);
  }
  const backup = `${desktopConfig}.bak-${Date.now()}`;
  fs.copyFileSync(desktopConfig, backup);
  console.log(`[OK] 기존 설정 백업: ${backup}`);
} else {
  fs.mkdirSync(path.dirname(desktopConfig), { recursive: true });
}
config.mcpServers = { ...(config.mcpServers ?? {}), [SERVER_NAME]: entry };
fs.writeFileSync(desktopConfig, JSON.stringify(config, null, 2) + "\n");
console.log(`[OK] Claude Desktop 등록: ${desktopConfig}`);

// 2) Claude Code CLI가 있으면 사용자 범위로 등록
try {
  execSync("claude --version", { stdio: "ignore" });
  try {
    execSync(`claude mcp remove --scope user ${SERVER_NAME}`, { stdio: "ignore" });
  } catch {}
  execSync(`claude mcp add --scope user ${SERVER_NAME} -- npx -y ${PACKAGE}`, { stdio: "inherit" });
  console.log("[OK] Claude Code 등록 (user scope)");
} catch {
  console.log("[--] Claude Code CLI 없음. Desktop 등록만 진행했습니다.");
}

// 3) 서버 패키지 미리 받아두기 (첫 실행 지연 방지)
try {
  execSync(`npm view ${PACKAGE} version`, { stdio: "inherit" });
  console.log("[OK] npm 패키지 확인");
} catch {
  console.log("[!] npm 패키지 조회 실패. 네트워크를 확인하세요.");
}

console.log(`
남은 수동 단계 (AE 안에서 한 번만 체크):
  After Effects > 환경설정 > 스크립팅 및 표현식
  > "Allow Scripts to Write Files and Access Network" 체크
${isWin ? "" : "  macOS: 첫 실행 때 뜨는 '자동화' 권한 요청 허용\n"}
그다음 Claude Desktop을 완전히 종료 후 다시 실행하세요.`);
