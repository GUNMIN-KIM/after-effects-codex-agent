/*
 * ae-swap-footage-suffix.jsx  v1.0
 *
 * 프로젝트에 이미 쓰이고 있는 영상만 "<원본 파일명><접미사>.<확장자>" 버전(기본 접미사 "_skin")으로 교체하고,
 * 그 영상을 쓰는 컴프의 기존 렌더 큐 항목(영상·첫 프레임·아웃 프레임 스틸 등)을
 * 같은 설정·같은 출력 경로로 다시 렌더한다.
 *
 * 교체 소스
 *   - Synology 폴더 공유 링크(https://<host>[:port]/sharing/<id>) → 프로젝트에 필요한 파일만 curl로 다운로드
 *   - 링크를 비워 두면, 이미 받아 둔 로컬/NAS 폴더를 고른다
 *
 * 보호 규칙 (AGENTS.md / references/operations-and-safety.md)
 *   - 원본 .aep는 덮어쓰지 않는다. "<프로젝트명><접미사>.aep"(이미 있으면 _v02, _v03 …)로 새로 저장한 뒤 작업한다.
 *   - 소스 파일만 바꾼다. 효과·LUT·마스크·키프레임·레이어 순서·컴프 설정·렌더 설정은 건드리지 않는다.
 *   - footage 해석(conform fps, alpha, field, loop, PAR)이 교체 후 달라지면 교체 전 값으로 되돌린다.
 *   - 기존 출력 파일은 지우지 않고 "<이름>_pre<접미사>.<확장자>"로 이름을 바꿔 보존한 뒤 같은 경로에 다시 렌더한다.
 *   - 파일명이 정확히 일치하지 않는 후보(접두 일치·컴프명 일치 등)는 확인 창에서 직접 켜야만 교체한다.
 *   - 모든 매핑·길이/fps/해상도 차이·다운로드·렌더 결과를 보고서(.txt)로 남긴다.
 *
 * 사용법
 *   1. After Effects 환경설정 > 스크립팅 및 표현식 > "스크립트가 파일을 쓰고 네트워크에 액세스하도록 허용"을 켠다.
 *   2. 대상 프로젝트를 열고 저장한다.
 *   3. 파일 > 스크립트 > 스크립트 파일 실행… 에서 이 파일을 고른다.
 *   4. 접미사(기본 _skin), 공유 링크(또는 폴더), 다운로드 위치를 확인하고 실행한다.
 *
 * 되돌리기: 원본 .aep를 다시 열면 된다(교체는 새 버전 파일에만 저장됨). 이전 출력물은 *_pre<접미사>.* 로 남아 있다.
 */
(function (global) {
    var SCRIPT_NAME = "Footage Suffix Swap";
    var SETTINGS_SECTION = "FootageSuffixSwap";
    var DEFAULT_SUFFIX = "_skin";

    // ------------------------------------------------------------------
    // 순수 함수 (AE 없이도 테스트 가능)
    // ------------------------------------------------------------------
    function trim(s) { return String(s).replace(/^\s+|\s+$/g, ""); }

    function splitExt(name) {
        var i = name.lastIndexOf(".");
        if (i <= 0) return { base: name, ext: "" };
        return { base: name.substring(0, i), ext: name.substring(i) };
    }

    function endsWith(s, tail) {
        return s.length >= tail.length && s.substring(s.length - tail.length) === tail;
    }

    function parseShareUrl(url) {
        var m = /^(https?:\/\/[^\/?#\s]+)\/sharing\/([A-Za-z0-9_\-]+)/.exec(trim(url));
        if (!m) return null;
        return { base: m[1], id: m[2] };
    }

    function decodeJsonUnicode(s) {
        return String(s).replace(/\\u([0-9a-fA-F]{4})/g, function (all, hex) {
            return String.fromCharCode(parseInt(hex, 16));
        }).replace(/\\\//g, "/");
    }

    // json2.js 방식: 구조를 검증한 뒤에만 eval (ExtendScript에는 JSON 객체가 없다)
    function safeJsonParse(text) {
        var t = String(text).replace(/[\u2028\u2029]/g, " ");
        var check = t.replace(/\\(?:["\\\/bfnrt]|u[0-9a-fA-F]{4})/g, "@")
            .replace(/"[^"\\\n\r]*"|true|false|null|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?/g, "]")
            .replace(/(?:^|:|,)(?:\s*\[)+/g, "");
        if (!/^[\],:{}\s]*$/.test(check)) throw new Error("서버 응답이 JSON이 아닙니다: " + t.substring(0, 200));
        return eval("(" + t + ")");
    }

    function jsonStr(s) {
        return '"' + String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"';
    }

    // skins: [{name, size}] → 접미사를 뗀 이름(소문자) 기준 색인
    function buildSkinIndex(skins, suffix) {
        var idx = { byCore: {}, list: [], dupes: [] };
        var sl = suffix.toLowerCase();
        for (var i = 0; i < skins.length; i++) {
            var bl = splitExt(skins[i].name).base.toLowerCase();
            if (!endsWith(bl, sl)) continue;
            var core = bl.substring(0, bl.length - sl.length);
            if (!core) continue;
            if (idx.byCore.hasOwnProperty(core)) { idx.dupes.push(skins[i].name); continue; }
            idx.byCore[core] = skins[i];
            idx.list.push({ core: core, skin: skins[i] });
        }
        return idx;
    }

    function exactCore(name, idx) {
        var bl = splitExt(name).base.toLowerCase();
        return idx.byCore.hasOwnProperty(bl) ? idx.byCore[bl] : null;
    }

    // 원본 이름이 "<core>" 다음에 _ - . 공백 중 하나로 이어지는 가장 긴 core
    function prefixCore(name, idx) {
        var bl = splitExt(name).base.toLowerCase();
        var best = null;
        for (var i = 0; i < idx.list.length; i++) {
            var c = idx.list[i].core;
            if (bl.length > c.length && bl.substring(0, c.length) === c &&
                    "_-. ".indexOf(bl.charAt(c.length)) !== -1) {
                if (!best || c.length > best.core.length) best = idx.list[i];
            }
        }
        return best ? best.skin : null;
    }

    // fileName: 원본 파일명, itemName: 프로젝트 패널 이름, compNames: 이 footage를 쓰는 컴프 이름들
    function matchFootage(fileName, itemName, compNames, idx, suffix) {
        var sl = suffix.toLowerCase();
        if (endsWith(splitExt(fileName).base.toLowerCase(), sl)) return { kind: "already" };
        var s = exactCore(fileName, idx);
        if (s) return { kind: "exact", skin: s, why: "파일명" };
        s = exactCore(itemName, idx);
        if (s) return { kind: "loose", skin: s, why: "프로젝트 항목 이름 '" + itemName + "'" };
        var found = null, foundComp = null, ambiguous = false;
        for (var i = 0; i < compNames.length; i++) {
            var c = exactCore(compNames[i], idx);
            if (!c) continue;
            if (found && found !== c) ambiguous = true;
            found = c; foundComp = compNames[i];
        }
        if (found && !ambiguous) return { kind: "loose", skin: found, why: "사용 컴프 이름 '" + foundComp + "'" };
        s = prefixCore(fileName, idx);
        if (s) return { kind: "loose", skin: s, why: "파일명 앞부분 일치" };
        return { kind: "none" };
    }

    // curl 설정 파일(-K) 생성: groups = [[[key, value?], ...], ...], 그룹 사이에 next
    function cfgQuote(s) {
        return '"' + String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"';
    }

    function cfgText(groups) {
        var out = [];
        for (var g = 0; g < groups.length; g++) {
            if (g > 0) out.push("next");
            for (var i = 0; i < groups[g].length; i++) {
                var o = groups[g][i];
                out.push(o.length > 1 && o[1] !== null && o[1] !== undefined ? o[0] + " = " + cfgQuote(o[1]) : o[0]);
            }
        }
        return out.join("\n") + "\n";
    }

    function synoGroups(share) {
        var common = [["silent"], ["show-error"], ["connect-timeout", "30"]];
        function withCommon(opts) { return opts.concat(common); }
        function cookies(jar) { return [["cookie", jar], ["cookie-jar", jar]]; }
        return {
            sessionInfo: function (outPath) {
                return withCommon([
                    ["url", share.base + "/sharing/webapi/entry.cgi"], ["get"],
                    ["data-urlencode", "api=SYNO.Core.Sharing.Session"],
                    ["data-urlencode", "version=1"],
                    ["data-urlencode", "method=get"],
                    ["data-urlencode", "sharing_id=" + jsonStr(share.id)],
                    ["data-urlencode", "sharing_status=" + jsonStr("none")],
                    ["output", outPath], ["max-time", "120"]
                ]);
            },
            // 공유 세션 쿠키 발급 + 초기화 (NAS가 IP 단위로 세션을 묶으므로 매 호출마다 같은 실행 안에서 다시 연다)
            open: function (jar, nullDev) {
                return [
                    withCommon([["url", share.base + "/sharing/" + share.id], ["output", nullDev], ["max-time", "120"]].concat(cookies(jar))),
                    withCommon([["url", share.base + "/sharing/webapi/entry.cgi?api=SYNO.Core.Sharing.Initdata&method=get&version=1"],
                        ["header", "X-SYNO-SHARING: " + share.id], ["output", nullDev], ["max-time", "120"]].concat(cookies(jar)))
                ];
            },
            list: function (jar, folder, outPath) {
                return withCommon([
                    ["url", share.base + "/sharing/webapi/entry.cgi"],
                    ["header", "X-SYNO-SHARING: " + share.id],
                    ["data-urlencode", "api=SYNO.FolderSharing.List"],
                    ["data-urlencode", "version=2"],
                    ["data-urlencode", "method=list"],
                    ["data-urlencode", "offset=0"],
                    ["data-urlencode", "limit=10000"],
                    ["data-urlencode", "sort_by=" + jsonStr("name")],
                    ["data-urlencode", "sort_direction=" + jsonStr("ASC")],
                    ["data-urlencode", "action=" + jsonStr("enum")],
                    ["data-urlencode", "additional=" + '["size"]'],
                    ["data-urlencode", "filetype=" + jsonStr("all")],
                    ["data-urlencode", "folder_path=" + jsonStr("/" + folder)],
                    ["data-urlencode", "_sharing_id=" + jsonStr(share.id)],
                    ["output", outPath], ["max-time", "300"]
                ].concat(cookies(jar)));
            },
            download: function (jar, folder, name, outPath, resume) {
                var opts = [
                    ["url", share.base + "/fsdownload/webapi/file_download.cgi/" + encodeURIComponent(name)], ["get"],
                    ["header", "X-SYNO-SHARING: " + share.id],
                    ["data-urlencode", "api=SYNO.FolderSharing.Download"],
                    ["data-urlencode", "version=2"],
                    ["data-urlencode", "method=download"],
                    ["data-urlencode", "mode=download"],
                    ["data-urlencode", "stdhtml=false"],
                    ["data-urlencode", "dlname=" + jsonStr(name)],
                    ["data-urlencode", "path=[" + jsonStr("/" + folder + "/" + name) + "]"],
                    ["data-urlencode", "_sharing_id=" + jsonStr(share.id)],
                    ["data-urlencode", "codepage=enu"],
                    ["fail"], ["output", outPath]
                ].concat(cookies(jar));
                if (resume) opts.push(["continue-at", "-"]);
                return withCommon(opts);
            }
        };
    }

    function fmtGB(bytes) { return (bytes / 1e9).toFixed(2) + " GB"; }

    function pad(s, n) { s = String(s); while (s.length < n) s += " "; return s; }

    if (typeof module !== "undefined" && module.exports) {
        module.exports = {
            trim: trim, splitExt: splitExt, parseShareUrl: parseShareUrl, safeJsonParse: safeJsonParse,
            decodeJsonUnicode: decodeJsonUnicode, buildSkinIndex: buildSkinIndex, matchFootage: matchFootage,
            cfgText: cfgText, synoGroups: synoGroups, jsonStr: jsonStr
        };
    }
    if (typeof app === "undefined") return;

    // ------------------------------------------------------------------
    // After Effects / 파일 시스템
    // ------------------------------------------------------------------
    var isWin = $.os.indexOf("Windows") !== -1;
    var NULL_DEV = isWin ? "NUL" : "/dev/null";
    var report = [];
    function log() { for (var i = 0; i < arguments.length; i++) report.push(arguments[i]); }

    function writeText(f, s, bom) {
        f.encoding = "UTF-8";
        if (!f.open("w")) throw new Error("파일을 쓸 수 없습니다: " + f.fsName);
        if (bom) f.write("\uFEFF");
        f.write(s);
        f.close();
    }

    function readText(f) {
        if (!f.exists) return "";
        f.encoding = "UTF-8";
        if (!f.open("r")) return "";
        var s = f.read();
        f.close();
        return s;
    }

    function getSetting(key, def) {
        try {
            if (app.settings.haveSetting(SETTINGS_SECTION, key)) return app.settings.getSetting(SETTINGS_SECTION, key);
        } catch (e) {}
        return def;
    }

    function saveSetting(key, val) {
        try { app.settings.saveSetting(SETTINGS_SECTION, key, val); } catch (e) {}
    }

    function shq(s) { return "'" + String(s).replace(/'/g, "'\\''") + "'"; }

    function findCurl() {
        if (isWin) {
            var root = $.getenv("SystemRoot") || "C:\\Windows";
            var f = new File(root + "\\System32\\curl.exe");
            return f.exists ? f.fsName : "curl.exe";
        }
        return "/usr/bin/curl";
    }

    // ---------------- 진행 창 ----------------
    var ui = null;
    function progress(msg, pct) {
        try {
            if (!ui) {
                ui = new Window("palette", SCRIPT_NAME);
                ui.alignChildren = "fill";
                ui.msg = ui.add("statictext", undefined, "", { multiline: true });
                ui.msg.preferredSize = [520, 44];
                ui.bar = ui.add("progressbar", undefined, 0, 100);
                ui.bar.preferredSize = [520, 12];
                ui.show();
            }
            ui.msg.text = msg;
            if (pct !== undefined) ui.bar.value = Math.max(0, Math.min(100, pct));
            ui.update();
        } catch (e) {}
    }
    function closeProgress() { try { if (ui) ui.close(); } catch (e) {} ui = null; }

    // ---------------- 네트워크 (Synology 공유) ----------------
    function SynoClient(share, ctlDir) {
        var curl = findCurl();
        var groups = synoGroups(share);
        var jar = ctlDir.fsName + (isWin ? "\\" : "/") + "_swap_cookies.txt";
        var cfg = new File(ctlDir.fsName + "/_swap_curl.cfg");

        function run(groupList) {
            var jf = new File(jar);
            if (jf.exists) jf.remove();
            writeText(cfg, cfgText(groupList), false);
            var cmd = isWin
                ? 'cmd.exe /c ""' + curl + '" -K "' + cfg.fsName + '" 2>&1 && echo SWAPOK"'
                : shq(curl) + " -K " + shq(cfg.fsName) + " 2>&1 && echo SWAPOK";
            var out = String(system.callSystem(cmd) || "");
            return { ok: /SWAPOK\s*$/.test(out), out: trim(out.replace(/SWAPOK\s*$/, "")) };
        }

        this.check = function () {
            var out = String(system.callSystem(isWin ? 'cmd.exe /c ""' + curl + '" --version"' : shq(curl) + " --version") || "");
            if (out.indexOf("curl") === -1) throw new Error("curl을 찾지 못했습니다 (" + curl + ").\nWindows 10 1803 이상 / macOS 기본 curl이 필요합니다.");
        };

        this.folderName = function () {
            var out = new File(ctlDir.fsName + "/_swap_session.txt");
            if (out.exists) out.remove();
            var r = run([groups.sessionInfo(out.fsName)]);
            var txt = readText(out);
            var m = /"filename"\s*:\s*"([^"]*)"/.exec(txt);
            var f = /"is_folder"\s*:\s*(true|false)/.exec(txt);
            var st = /"sharing_status"\s*:\s*"([^"]*)"/.exec(txt);
            if (!m) throw new Error("공유 링크 정보를 읽지 못했습니다.\n" + r.out + "\n" + txt.substring(0, 300));
            if (st && st[1] !== "none") throw new Error("공유 링크 상태가 '" + st[1] + "'입니다 (만료·비밀번호 보호·비활성). 브라우저로 링크가 열리는지 확인하세요.");
            if (f && f[1] !== "true") throw new Error("폴더 공유 링크가 아닙니다. 폴더를 공유한 링크가 필요합니다.");
            return decodeJsonUnicode(m[1]);
        };

        this.list = function (folder) {
            var out = new File(ctlDir.fsName + "/_swap_list.json");
            if (out.exists) out.remove();
            var r = run(groups.open(jar, NULL_DEV).concat([groups.list(jar, folder, out.fsName)]));
            var txt = readText(out);
            if (!txt) throw new Error("공유 폴더 목록을 받지 못했습니다.\n" + r.out);
            var data = safeJsonParse(txt);
            if (!data.success) throw new Error("공유 폴더 목록 조회 실패 (Synology 오류 코드 " + (data.error ? data.error.code : "?") + ")");
            var res = [], files = data.data.files || [];
            for (var i = 0; i < files.length; i++) {
                if (files[i].isdir) continue;
                res.push({ name: files[i].name, size: files[i].additional && files[i].additional.size !== undefined ? files[i].additional.size : -1 });
            }
            return res;
        };

        // 반환: {status: "present"|"downloaded"|"mismatch"|"error", detail}
        this.download = function (folder, skin, destDir) {
            var finalF = new File(destDir.fsName + "/" + skin.name);
            // 2GB를 넘는 파일은 File.length를 믿지 않고 curl 정상 종료(-f, Content-Length 만큼 수신)를 완료 기준으로 본다
            var big = skin.size > 2147483647;
            // Synology는 실패해도 HTTP 200 + 작은 JSON({"error":{"code":…}})을 돌려주므로 작은 파일은 완료로 보지 않는다
            function complete(f, curlOk) {
                if (!f.exists) return false;
                if (skin.size < 0) return curlOk && f.length > 1048576;
                return f.length === skin.size || (big && curlOk && f.length > 1048576);
            }
            function synoError(f) {
                if (!f.exists || f.length > 4096) return "";
                var m = /"code"\s*:\s*(\d+)/.exec(readText(f));
                return m ? "Synology 오류 코드 " + m[1] + " (공유 만료·권한·파일 없음)" : "";
            }
            if (finalF.exists) {
                if (complete(finalF, !big)) return { status: "present" };
                if (big && finalF.length > 0) return { status: "present", detail: "2GB 초과 파일 — 크기 확인 생략, 이미 있는 파일 사용" };
                return { status: "mismatch", detail: "같은 이름 파일이 이미 있으나 크기가 다름 (" + finalF.length + " / " + skin.size + " bytes) — 건드리지 않음" };
            }
            var partPath = destDir.fsName + "/" + skin.name + ".part";
            var last = "", done = false;
            for (var attempt = 1; attempt <= 3 && !done; attempt++) {
                var part = new File(partPath);
                if (complete(part, false)) { done = true; break; }
                var resume = part.exists && part.length > 0 && attempt < 3;
                if (!resume && part.exists) part.remove();
                var r = run(groups.open(jar, NULL_DEV).concat([groups.download(jar, folder, skin.name, partPath, resume)]));
                last = r.out;
                var pf = new File(partPath);
                done = complete(pf, r.ok);
                var se = done ? "" : synoError(pf);
                if (se) { last = se; pf.remove(); break; }
            }
            if (done) {
                if (new File(partPath).rename(skin.name)) return { status: "downloaded" };
                return { status: "error", detail: "다운로드는 끝났지만 이름 변경 실패: " + partPath };
            }
            return { status: "error", detail: last || "알 수 없는 오류 (경로에 한글이 있으면 영문 경로로 다시 시도)" };
        };
    }

    // ---------------- 로컬 폴더 / 휴지통 ----------------
    var BUSY_EXT = /\.(part|crdownload|download|partial|tmp)$/i;

    // 폴더 바로 아래 파일만. 아직 받는 중인 파일(.crdownload/.part 짝이 있거나 0바이트)과 숨김 파일은 제외
    function scanFolder(dir) {
        var res = { files: [], busy: [] };
        if (!dir || !dir.exists) return res;
        var all = dir.getFiles(), names = {};
        for (var i = 0; i < all.length; i++) names[File.decode(all[i].name).toLowerCase()] = true;
        for (var j = 0; j < all.length; j++) {
            var f = all[j];
            if (!(f instanceof File)) continue;
            var n = File.decode(f.name), nl = n.toLowerCase();
            if (n.charAt(0) === "." || BUSY_EXT.test(n)) continue;
            if (f.length <= 0 || names[nl + ".part"] || names[nl + ".crdownload"] || names[nl + ".download"]) { res.busy.push(n); continue; }
            res.files.push({ name: n, size: f.length, file: f });
        }
        return res;
    }

    // macOS: Finder 휴지통(되돌리기 가능). Windows: 휴지통(용량 초과로 영구 삭제될 땐 Windows가 먼저 경고)
    function moveToTrash(files, ctlDir) {
        var out = "";
        if (files.length) {
            if (isWin) {
                var L = [
                    "$ErrorActionPreference = 'Stop'",
                    "Add-Type -TypeDefinition @'",
                    "using System;",
                    "using System.Runtime.InteropServices;",
                    "public static class FootageSwapTrash {",
                    "    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]",
                    "    private struct SHFILEOPSTRUCT {",
                    "        public IntPtr hwnd; public uint wFunc;",
                    "        [MarshalAs(UnmanagedType.LPWStr)] public string pFrom;",
                    "        [MarshalAs(UnmanagedType.LPWStr)] public string pTo;",
                    "        public ushort fFlags;",
                    "        [MarshalAs(UnmanagedType.Bool)] public bool fAnyOperationsAborted;",
                    "        public IntPtr hNameMappings;",
                    "        [MarshalAs(UnmanagedType.LPWStr)] public string lpszProgressTitle;",
                    "    }",
                    "    [DllImport(\"shell32.dll\", CharSet = CharSet.Unicode)]",
                    "    private static extern int SHFileOperation(ref SHFILEOPSTRUCT op);",
                    "    public static int Recycle(string[] paths) {",
                    "        SHFILEOPSTRUCT op = new SHFILEOPSTRUCT();",
                    "        op.wFunc = 3; // FO_DELETE",
                    "        op.pFrom = string.Join(\"\\0\", paths) + \"\\0\\0\";",
                    "        op.fFlags = (ushort)(0x0040 | 0x0010 | 0x4000); // ALLOWUNDO | NOCONFIRMATION | WANTNUKEWARNING",
                    "        int r = SHFileOperation(ref op);",
                    "        return (r == 0 && op.fAnyOperationsAborted) ? -1 : r;",
                    "    }",
                    "}",
                    "'@",
                    "$paths = @("
                ];
                for (var i = 0; i < files.length; i++) L.push("  '" + files[i].fsName.replace(/'/g, "''") + "'" + (i < files.length - 1 ? "," : ""));
                L.push(")", "$r = [FootageSwapTrash]::Recycle([string[]]$paths)", "Write-Output \"TRASHRESULT $r\"");
                var ps = new File(ctlDir.fsName + "/_swap_trash.ps1");
                writeText(ps, L.join("\r\n"), true);
                out = system.callSystem('cmd.exe /c ""powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "' + ps.fsName + '" 2>&1"');
            } else {
                var args = [];
                for (var k = 0; k < files.length; k++) args.push(shq(files[k].fsName));
                out = system.callSystem("/usr/bin/osascript -e 'on run argv' -e 'repeat with p in argv' -e 'set f to POSIX file (p as text)'" +
                    " -e 'tell application \"Finder\" to delete (f as alias)' -e 'end repeat' -e 'end run' " + args.join(" ") + " 2>&1");
            }
        }
        var res = { trashed: [], left: [], out: trim(String(out || "")) };
        for (var m = 0; m < files.length; m++) (new File(files[m].fsName).exists ? res.left : res.trashed).push(File.decode(files[m].name));
        return res;
    }

    // ---------------- 프로젝트 조사 ----------------
    function collectFootage(proj) {
        var res = [];
        for (var i = 1; i <= proj.numItems; i++) {
            var it = proj.item(i);
            if (!(it instanceof FootageItem)) continue;
            if (!(it.mainSource instanceof FileSource)) continue;
            var f = it.mainSource.file;
            if (!f) continue;
            var comps = [];
            for (var j = 0; j < it.usedIn.length; j++) comps.push(it.usedIn[j].name);
            res.push({
                item: it, file: f, fileName: File.decode(f.name), itemName: it.name, compNames: comps,
                used: it.usedIn.length > 0, still: it.mainSource.isStill
            });
        }
        return res;
    }

    function snapshot(it) {
        var s = { path: "", name: it.name };
        function g(k, fn) { try { s[k] = fn(); } catch (e) { s[k] = undefined; } }
        g("path", function () { return it.mainSource.file.fsName; });
        g("duration", function () { return it.duration; });
        g("frameRate", function () { return it.frameRate; });
        g("width", function () { return it.width; });
        g("height", function () { return it.height; });
        g("pixelAspect", function () { return it.pixelAspect; });
        g("conformFrameRate", function () { return it.mainSource.conformFrameRate; });
        g("alphaMode", function () { return it.mainSource.alphaMode; });
        g("fieldSeparationType", function () { return it.mainSource.fieldSeparationType; });
        g("loop", function () { return it.mainSource.loop; });
        return s;
    }

    function restoreInterpretation(it, before, after, notes) {
        var keys = [["conformFrameRate", it.mainSource], ["alphaMode", it.mainSource], ["fieldSeparationType", it.mainSource],
            ["loop", it.mainSource], ["pixelAspect", it]];
        for (var i = 0; i < keys.length; i++) {
            var k = keys[i][0];
            if (before[k] === undefined || before[k] === after[k]) continue;
            try { keys[i][1][k] = before[k]; notes.push(k + " " + after[k] + " → " + before[k] + " 복원"); }
            catch (e) { notes.push(k + " 복원 실패(" + before[k] + "): " + e.message); }
        }
    }

    function fmtTime(sec, fps) {
        if (sec === undefined) return "?";
        return sec.toFixed(3) + "s" + (fps ? " (" + Math.round(sec * fps) + "f)" : "");
    }

    function affectedComps(items) {
        var set = {}, list = [], queue = [];
        function add(c) { if (!set.hasOwnProperty(c.id)) { set[c.id] = c; list.push(c); queue.push(c); } }
        for (var i = 0; i < items.length; i++) {
            var u = items[i].usedIn;
            for (var j = 0; j < u.length; j++) add(u[j]);
        }
        while (queue.length) {
            var c = queue.shift(), u2 = c.usedIn;
            for (var k = 0; k < u2.length; k++) add(u2[k]);
        }
        return { set: set, list: list };
    }

    function findLutEffects(comps) {
        var res = [];
        for (var i = 0; i < comps.length; i++) {
            var c = comps[i];
            for (var l = 1; l <= c.numLayers; l++) {
                var layer = c.layer(l), fx = null;
                try { fx = layer.property("ADBE Effect Parade"); } catch (e) {}
                if (!fx) continue;
                for (var e2 = 1; e2 <= fx.numProperties; e2++) {
                    var p = fx.property(e2);
                    if (/LUT|Lumetri|OCIO/i.test(p.matchName) || /LUT|Lumetri/i.test(p.name)) {
                        res.push(c.name + " › " + layer.name + " › " + p.name + (p.enabled ? "" : " (꺼짐)"));
                    }
                }
            }
        }
        return res;
    }

    function renderTemplates(rq, compSet) {
        var seen = {}, res = [];
        for (var i = rq.numItems; i >= 1; i--) {
            var it = rq.item(i), c = null;
            try { c = it.comp; } catch (e) {}
            if (!c || !compSet.hasOwnProperty(c.id)) continue;
            var paths = [];
            for (var j = 1; j <= it.numOutputModules; j++) {
                var f = null;
                try { f = it.outputModule(j).file; } catch (e2) {}
                paths.push(f ? f.fsName : "");
            }
            var key = c.id + "|" + paths.join("|") + "|" + it.timeSpanStart.toFixed(4) + "|" + it.timeSpanDuration.toFixed(4);
            if (seen[key]) continue;
            seen[key] = true;
            // 인덱스가 아니라 객체를 보관한다 (duplicate()가 원본 바로 아래에 끼워 넣으면 인덱스가 밀린다)
            res.unshift({ item: it, comp: c, paths: paths, start: it.timeSpanStart, dur: it.timeSpanDuration });
        }
        return res;
    }

    function rqLabel(t) {
        var fd = t.comp.frameDuration;
        if (t.dur > fd * 1.5) return "영상";
        if (Math.abs(t.start) < fd / 2) return "첫 프레임";
        if (Math.abs(t.start - (t.comp.duration - fd)) < fd / 2) return "아웃 프레임";
        return "프레임 @" + Math.round(t.start / fd) + "f";
    }

    function backupOutput(path, tag) {
        if (!path) return { note: "출력 경로 없음" };
        var f = new File(path);
        var nm = File.decode(f.name);
        if (/\[#+\]/.test(nm)) return { note: "시퀀스 출력 — 같은 경로에 덮어씀(백업 안 함)" };
        if (!f.exists) return { note: "기존 파일 없음" };
        var p = splitExt(nm), dir = f.parent.fsName, n = p.base + tag + p.ext, k = 2;
        while (new File(dir + "/" + n).exists) { n = p.base + tag + k + p.ext; k++; }
        if (f.rename(n)) return { note: "기존 파일 → " + n };
        return { note: "백업 이름 변경 실패 — 이 출력은 건너뜀", fail: true };
    }

    function nextVersionFile(projFile, suffix) {
        var p = splitExt(File.decode(projFile.name)), dir = projFile.parent.fsName;
        var f = new File(dir + "/" + p.base + suffix + ".aep"), n = 2;
        while (f.exists) {
            f = new File(dir + "/" + p.base + suffix + "_v" + (n < 10 ? "0" : "") + n + ".aep");
            n++;
        }
        return f;
    }

    // ---------------- 확인 창 ----------------
    function confirmDialog(summary, details, looseCount, canRender, trashCount, trashBytes) {
        var d = new Window("dialog", SCRIPT_NAME);
        d.alignChildren = "fill";
        d.add("statictext", undefined, summary, { multiline: true }).preferredSize = [680, 90];
        var t = d.add("edittext", undefined, details, { multiline: true, readonly: true, scrolling: true });
        t.preferredSize = [680, 340];
        var cbLoose = d.add("checkbox", undefined, "파일명이 정확히 같지 않은 후보 " + looseCount + "개도 교체 (위 목록 '확인 필요' 확인 후)");
        cbLoose.value = false;
        cbLoose.enabled = looseCount > 0;
        var cbRender = d.add("checkbox", undefined, "교체 후 기존 렌더 큐 설정 그대로 다시 렌더 (영상·첫/아웃 프레임, 같은 경로, 기존 파일은 백업)");
        cbRender.value = canRender;
        cbRender.enabled = canRender;
        var cbTrash = d.add("checkbox", undefined, "에펙 프로젝트에 없는 영상 " + trashCount + "개 (" + fmtGB(trashBytes || 0) + ") 휴지통으로 보내기 — 위 목록 '[휴지통으로]' 확인");
        cbTrash.value = trashCount > 0;
        cbTrash.enabled = trashCount > 0;
        var g = d.add("group");
        g.alignment = "right";
        g.add("button", undefined, "취소", { name: "cancel" });
        g.add("button", undefined, "실행", { name: "ok" });
        if (d.show() !== 1) return null;
        return { loose: cbLoose.value, render: cbRender.value, trash: cbTrash.value && trashCount > 0 };
    }

    // ------------------------------------------------------------------
    // main
    // ------------------------------------------------------------------
    function main() {
        var proj = app.project;
        if (!proj || !proj.file) { alert("먼저 대상 프로젝트를 열고 저장하세요.", SCRIPT_NAME); return; }
        try {
            var probe = new File(Folder.temp.fsName + "/_footage_suffix_swap_probe.txt");
            writeText(probe, "ok", false);
            probe.remove();
        } catch (e) {
            alert("환경설정 > 스크립팅 및 표현식 > '스크립트가 파일을 쓰고 네트워크에 액세스하도록 허용'을 켠 뒤 다시 실행하세요.", SCRIPT_NAME);
            return;
        }

        var origProjPath = proj.file.fsName;
        log(SCRIPT_NAME + " 보고서  " + new Date().toString());
        log("원본 프로젝트: " + origProjPath + " (변경 안 함)");

        // 1. UNDERSTAND
        var suffix = prompt("교체할 파일 접미사 (원본 이름 + 접미사)", getSetting("suffix", DEFAULT_SUFFIX), SCRIPT_NAME);
        if (suffix === null) return;
        suffix = trim(suffix);
        if (!suffix) { alert("접미사가 비어 있습니다.", SCRIPT_NAME); return; }
        saveSetting("suffix", suffix);

        var url = prompt("Synology 폴더 공유 링크 (https://…/sharing/…)\n비워 두면 이미 받아 둔 폴더를 직접 고릅니다.", getSetting("shareUrl", ""), SCRIPT_NAME);
        if (url === null) return;
        url = trim(url);

        // 2. INSPECT
        var footage = collectFootage(proj);
        var skins, share = null, client = null, remoteFolder = null, srcDir = null;
        var ctlDir = new Folder(Folder.temp.fsName + "/ae_footage_suffix_swap");
        if (!ctlDir.exists) ctlDir.create();

        if (url) {
            share = parseShareUrl(url);
            if (!share) { alert("공유 링크 형식이 아닙니다: " + url + "\n예) https://<NAS 주소>:5001/sharing/AbCdEf", SCRIPT_NAME); return; }
            saveSetting("shareUrl", url);
            client = new SynoClient(share, ctlDir);
            progress("공유 링크 확인 중…", 2);
            client.check();
            remoteFolder = client.folderName();
            progress("공유 폴더 '" + remoteFolder + "' 목록 읽는 중…", 5);
            skins = client.list(remoteFolder);
            log("공유 폴더: " + remoteFolder + " (" + skins.length + "개 파일)");
        } else {
            srcDir = Folder.selectDialog("교체할 '*" + suffix + "' 영상이 있는 폴더를 고르세요");
            if (!srcDir) return;
            var loc = scanFolder(srcDir);
            skins = loc.files;
            log("로컬 소스 폴더: " + srcDir.fsName + " (" + skins.length + "개 파일)");
            if (loc.busy.length) log("※ 아직 받는 중이라 제외(교체·휴지통 모두 안 함): " + loc.busy.join(", "));
        }

        var idx = buildSkinIndex(skins, suffix);
        if (idx.dupes.length) log("※ 소스에 같은 이름(대소문자만 다른) 파일이 있어 첫 번째만 사용: " + idx.dupes.join(", "));

        // 3. PLAN
        var plan = [], unmatched = [], already = [], unused = [], stills = [];
        var keep = {}; // 프로젝트 어딘가에 대응하는 파일 이름(소문자) — 휴지통 대상에서 제외
        for (var a = 0; a < footage.length; a++) {
            var ft = footage[a];
            keep[ft.fileName.toLowerCase()] = true;
            var m = matchFootage(ft.fileName, ft.itemName, ft.compNames, idx, suffix);
            if (m.skin) keep[m.skin.name.toLowerCase()] = true;
            if (m.kind === "already") { already.push(ft.fileName); continue; }
            if (m.kind === "none") { if (ft.used && !ft.still) unmatched.push(ft.fileName); continue; }
            if (ft.still) { stills.push(ft.fileName + " → " + m.skin.name); continue; }
            if (!ft.used) { unused.push(ft.fileName + " → " + m.skin.name); continue; }
            plan.push({ ft: ft, kind: m.kind, why: m.why, skin: m.skin });
        }

        // 짝을 못 찾은 원본(예: …_D09)과 이름이 이어지는 소스(…_D09L_skin, …_D09R_skin)는 관련 있을 수 있으니 휴지통에서 뺀다
        var related = [];
        for (var un = 0; un < unmatched.length; un++) {
            var ub = splitExt(unmatched[un]).base.toLowerCase();
            for (var ul = 0; ul < idx.list.length; ul++) {
                if (idx.list[ul].core.indexOf(ub) === 0 && !keep[idx.list[ul].skin.name.toLowerCase()]) {
                    keep[idx.list[ul].skin.name.toLowerCase()] = true;
                    related.push(unmatched[un] + "  ~  " + idx.list[ul].skin.name);
                }
            }
        }

        var exactN = 0, looseN = 0;
        for (var b = 0; b < plan.length; b++) { if (plan[b].kind === "exact") exactN++; else looseN++; }

        var compSetAll = affectedComps((function () { var r = []; for (var i2 = 0; i2 < plan.length; i2++) r.push(plan[i2].ft.item); return r; })());
        var tplPreview = plan.length ? renderTemplates(proj.renderQueue, compSetAll.set) : [];

        var det = [];
        det.push("[교체 — 파일명 일치]");
        for (var c1 = 0; c1 < plan.length; c1++) if (plan[c1].kind === "exact") det.push("  " + plan[c1].ft.fileName + "  →  " + plan[c1].skin.name);
        if (looseN) {
            det.push("", "[확인 필요 — 체크해야 교체]");
            for (var c2 = 0; c2 < plan.length; c2++) if (plan[c2].kind !== "exact") det.push("  " + plan[c2].ft.fileName + "  →  " + plan[c2].skin.name + "   (" + plan[c2].why + ")");
        }
        if (unmatched.length) { det.push("", "[짝 없음 — 그대로 둠]"); for (var c3 = 0; c3 < unmatched.length; c3++) det.push("  " + unmatched[c3]); }
        if (related.length) { det.push("", "[짝 없음 원본과 이름이 이어지는 소스 — 교체도 휴지통도 안 함, 직접 확인]"); for (var c3b = 0; c3b < related.length; c3b++) det.push("  " + related[c3b]); }
        if (unused.length) { det.push("", "[컴프에서 안 쓰는 항목 — 그대로 둠]"); for (var c4 = 0; c4 < unused.length; c4++) det.push("  " + unused[c4]); }
        if (stills.length) { det.push("", "[스틸 이미지 — 그대로 둠]"); for (var c5 = 0; c5 < stills.length; c5++) det.push("  " + stills[c5]); }
        if (already.length) { det.push("", "[이미 '" + suffix + "' 소스 — 그대로 둠]"); for (var c6 = 0; c6 < already.length; c6++) det.push("  " + already[c6]); }
        det.push("", "[다시 렌더할 기존 렌더 큐 항목: " + tplPreview.length + "개]");
        for (var c7 = 0; c7 < tplPreview.length; c7++) det.push("  " + tplPreview[c7].comp.name + " · " + rqLabel(tplPreview[c7]) + " · " + tplPreview[c7].paths.join(" | "));

        if (!plan.length && !already.length) {
            closeProgress();
            alert("교체할 영상이 없습니다.\n\n" + det.join("\n").substring(0, 1500), SCRIPT_NAME);
            return;
        }

        // 다운로드 위치 (휴지통 후보를 미리 보여주려고 확인 창 전에 정한다)
        var destDir = srcDir;
        if (share) {
            closeProgress();
            destDir = new Folder(proj.file.parent.fsName + "/" + remoteFolder);
            if (!confirm("교체 영상 받을 위치(이미 받아 둔 파일은 크기 확인 후 그대로 사용):\n" + destDir.fsName + "\n\n이 위치를 쓸까요? (아니오 → 직접 선택)", false, SCRIPT_NAME)) {
                destDir = Folder.selectDialog("교체 영상을 받을(또는 이미 받아 둔) 폴더를 고르세요");
                if (!destDir) return;
            }
        }

        // 휴지통 후보: 그 폴더의 '*<접미사>' 파일 중 프로젝트 어디에도 대응하지 않는 것
        var trashList = [], trashBytes = 0, scanned = scanFolder(destDir);
        if (scanned.busy.length && share) log("※ 아직 받는 중이라 제외: " + scanned.busy.join(", "));
        for (var tz = 0; tz < scanned.files.length; tz++) {
            var sf = scanned.files[tz];
            if (!endsWith(splitExt(sf.name).base.toLowerCase(), suffix.toLowerCase())) continue;
            if (keep[sf.name.toLowerCase()]) continue;
            trashList.push(sf.file);
            trashBytes += sf.size;
        }
        if (trashList.length) {
            det.push("", "[휴지통으로 — 에펙 프로젝트에 없는 영상 " + trashList.length + "개, " + fmtGB(trashBytes) + "]");
            for (var tz2 = 0; tz2 < trashList.length; tz2++) det.push("  " + File.decode(trashList[tz2].name));
        }
        if (scanned.busy.length) {
            det.push("", "[아직 받는 중 — 건드리지 않음]");
            for (var tz3 = 0; tz3 < scanned.busy.length; tz3++) det.push("  " + scanned.busy[tz3]);
        }

        var dlBytesExact = 0, dlBytesAll = 0, seenSkin = {};
        for (var d1 = 0; d1 < plan.length; d1++) {
            var sk = plan[d1].skin;
            if (seenSkin[sk.name]) continue;
            seenSkin[sk.name] = true;
            if (sk.size > 0) { dlBytesAll += sk.size; if (plan[d1].kind === "exact") dlBytesExact += sk.size; }
        }

        var summary = "교체 대상 " + plan.length + "개 (파일명 일치 " + exactN + " · 확인 필요 " + looseN + ") / 짝 없음 " + unmatched.length + "\n" +
            (share ? "다운로드 최대 " + fmtGB(dlBytesExact) + (looseN ? " (확인 필요 포함 시 " + fmtGB(dlBytesAll) + ")" : "") + " — 이미 받은 파일은 건너뜀\n" : "") +
            "원본 .aep는 그대로 두고 '" + nextVersionFile(proj.file, suffix).displayName + "'로 새로 저장한 뒤 작업합니다.\n" +
            "효과·LUT·키프레임·렌더 설정은 건드리지 않습니다.";
        closeProgress();
        // 파일명이 정확히 맞은 게 하나도 없으면 이름 규칙이 다른 것 — 휴지통은 막는다
        var canTrash = trashList.length > 0 && (exactN > 0 || already.length > 0);
        var choice = confirmDialog(summary, det.join("\n"), looseN, tplPreview.length > 0, canTrash ? trashList.length : 0, trashBytes);
        if (!choice) return;

        var work = [];
        for (var w1 = 0; w1 < plan.length; w1++) if (plan[w1].kind === "exact" || choice.loose) work.push(plan[w1]);
        if (!work.length && !choice.trash) { alert("선택된 작업이 없습니다.", SCRIPT_NAME); return; }

        if (share && !destDir.exists && !destDir.create()) { alert("폴더를 만들 수 없습니다: " + destDir.fsName, SCRIPT_NAME); return; }
        log("교체 영상 위치: " + destDir.fsName);

        // 4. PROTECT — 새 버전으로 저장
        // 교체할 게 없으면(휴지통만) 프로젝트는 저장하지 않는다
        var newProj = work.length ? nextVersionFile(proj.file, suffix) : proj.file;
        if (work.length) {
            proj.save(newProj);
            log("작업 프로젝트(새 버전): " + newProj.fsName);
        } else {
            log("교체할 영상 없음 — 프로젝트는 저장하지 않음");
        }

        // 5. 다운로드 (필요한 것만)
        var ready = {}, dlLog = [];
        var uniq = [], seen2 = {};
        for (var u1 = 0; u1 < work.length; u1++) if (!seen2[work[u1].skin.name]) { seen2[work[u1].skin.name] = true; uniq.push(work[u1].skin); }
        for (var u2 = 0; u2 < uniq.length; u2++) {
            var s2 = uniq[u2];
            if (share) {
                progress("다운로드 " + (u2 + 1) + "/" + uniq.length + "  " + s2.name + "  (" + fmtGB(s2.size) + ")\n큰 파일은 AE가 잠시 멈춘 것처럼 보일 수 있습니다.", 5 + 60 * u2 / uniq.length);
                var res = client.download(remoteFolder, s2, destDir);
                dlLog.push(pad(res.status, 11) + s2.name + (res.detail ? "  — " + res.detail : ""));
                if (res.status === "present" || res.status === "downloaded") ready[s2.name] = new File(destDir.fsName + "/" + s2.name);
            } else {
                ready[s2.name] = new File(destDir.fsName + "/" + s2.name);
            }
        }
        if (share) { log("", "[다운로드]"); for (var u3 = 0; u3 < dlLog.length; u3++) log("  " + dlLog[u3]); }

        // 6. EXECUTE + RE-INSPECT — 소스 교체
        progress("소스 교체 중…", 68);
        app.beginUndoGroup(SCRIPT_NAME);
        var replaced = [], failed = [];
        log("", "[소스 교체]");
        for (var r1 = 0; r1 < work.length; r1++) {
            var job = work[r1], it = job.ft.item, nf = ready[job.skin.name];
            if (!nf || !nf.exists) { failed.push(job); log("  실패  " + job.ft.fileName + " — 교체 파일 없음(다운로드 실패)"); continue; }
            var before = snapshot(it);
            try { it.replace(nf); }
            catch (e3) { failed.push(job); log("  실패  " + job.ft.fileName + " — " + e3.message); continue; }
            var after = snapshot(it), notes = [];
            restoreInterpretation(it, before, after, notes);
            after = snapshot(it);
            if (after.path !== nf.fsName) notes.push("재조회 경로 불일치: " + after.path);
            var fd = before.frameRate ? 1 / before.frameRate : 0.04;
            // 길이가 다르면 핸들·구간이 달라 같은 레이어 시간에 다른 프레임이 나올 수 있다 (짧으면 끝이 비기도 함)
            if (before.duration !== undefined && Math.abs(after.duration - before.duration) > fd / 2) {
                notes.push("⚠ 길이 다름 " + fmtTime(before.duration, before.frameRate) + " → " + fmtTime(after.duration, after.frameRate) +
                    " — 구간/핸들이 다르면 프레임이 밀림. 첫/아웃 프레임을 백업본과 비교할 것" +
                    (after.duration < before.duration ? " (짧아서 레이어 끝이 비어 보일 수 있음)" : ""));
            }
            if (before.frameRate !== undefined && Math.abs(after.frameRate - before.frameRate) > 0.001) notes.push("⚠ fps " + before.frameRate + " → " + after.frameRate);
            if (before.width !== after.width || before.height !== after.height) notes.push("⚠ 해상도 " + before.width + "x" + before.height + " → " + after.width + "x" + after.height);
            replaced.push({ job: job, notes: notes });
            log("  " + (job.kind === "exact" ? "교체" : "교체*") + "  " + before.path + "\n        → " + after.path + (job.kind !== "exact" ? "   (" + job.why + ")" : "") +
                (notes.length ? "\n        " + notes.join("\n        ") : ""));
        }
        app.endUndoGroup();
        if (work.length) proj.save();

        // 에펙 프로젝트에 없는 영상 → 휴지통 (교체·저장이 끝난 뒤, 확인 창에 보여 준 목록만)
        var trashRes = null;
        if (choice.trash) {
            progress("프로젝트에 없는 영상 " + trashList.length + "개를 휴지통으로 보내는 중…", 70);
            var still = [];
            for (var tq = 0; tq < trashList.length; tq++) if (new File(trashList[tq].fsName).exists) still.push(trashList[tq]);
            trashRes = moveToTrash(still, ctlDir);
            log("", "[휴지통 — 에펙 프로젝트에 없는 영상]");
            for (var tr1 = 0; tr1 < trashRes.trashed.length; tr1++) log("  휴지통  " + trashRes.trashed[tr1]);
            for (var tr2 = 0; tr2 < trashRes.left.length; tr2++) log("  남음    " + trashRes.left[tr2]);
            if (trashRes.left.length) log("  " + (isWin ? "휴지통 이동이 취소/실패됨: " : "Finder 제어 권한(시스템 설정 > 개인정보 보호 및 보안 > 자동화)을 확인: ") + trashRes.out.substring(0, 300));
        }

        // LUT 등 그대로 유지됐는지 기록 (읽기 전용)
        var repItems = [];
        for (var r2 = 0; r2 < replaced.length; r2++) repItems.push(replaced[r2].job.ft.item);
        var comps = affectedComps(repItems);
        var luts = findLutEffects(comps.list);
        log("", "[LUT/색 효과 — 변경 안 함, 확인용]");
        if (luts.length) for (var r3 = 0; r3 < luts.length; r3++) log("  " + luts[r3]);
        else log("  영향받는 컴프에서 LUT/Lumetri/OCIO 효과를 찾지 못함 (다른 방식으로 적용돼 있으면 무시)");

        // 7. RENDER — 기존 렌더 큐 항목을 같은 설정·같은 경로로
        var rq = proj.renderQueue, rendered = [];
        var tpls = replaced.length ? renderTemplates(rq, comps.set) : [];
        var compsNoHistory = [];
        for (var r4 = 0; r4 < repItems.length; r4++) {
            var u4 = repItems[r4].usedIn;
            for (var r5 = 0; r5 < u4.length; r5++) {
                var has = false;
                for (var r6 = 0; r6 < tpls.length; r6++) if (tpls[r6].comp.id === u4[r5].id) { has = true; break; }
                if (!has) {
                    var dup = false;
                    for (var r7 = 0; r7 < compsNoHistory.length; r7++) if (compsNoHistory[r7] === u4[r5].name) dup = true;
                    if (!dup) compsNoHistory.push(u4[r5].name);
                }
            }
        }

        if (choice.render && tpls.length) {
            progress("렌더 큐 준비 중…", 72);
            var newIdx = [], tag = "_pre" + suffix.replace(/^_+/, "");
            log("", "[렌더 — 기존 렌더 큐 설정 복제]");

            // 기존에 대기 중이던 항목은 잠시 빼 두고(끝나면 반드시 복원), 새로 넣은 항목만 렌더한다
            var parked = [];
            for (var p1 = 1; p1 <= rq.numItems; p1++) {
                try { var pi = rq.item(p1); if (pi.status === RQItemStatus.QUEUED) { pi.render = false; parked.push(pi); } } catch (e6) {}
            }

            try {
                for (var t1 = 0; t1 < tpls.length; t1++) {
                    var tp = tpls[t1], label = tp.comp.name + " · " + rqLabel(tp);
                    var hasPath = false;
                    for (var t0 = 0; t0 < tp.paths.length; t0++) if (tp.paths[t0]) hasPath = true;
                    if (!hasPath) { log("  건너뜀  " + label + " — 출력 경로 없음"); continue; }
                    // 복제·경로 설정이 끝난 뒤에만 기존 출력을 백업한다 (실패하면 기존 파일은 그대로)
                    var nu;
                    try {
                        nu = tp.item.duplicate();
                        for (var t3 = 0; t3 < tp.paths.length; t3++) if (tp.paths[t3]) nu.outputModule(t3 + 1).file = new File(tp.paths[t3]);
                    } catch (e4) {
                        log("  실패  " + label + " — 렌더 큐 복제/경로 설정 실패: " + e4.message);
                        try { if (nu) nu.remove(); } catch (e4b) {}
                        continue;
                    }
                    var backups = [], skip = false;
                    for (var t2 = 0; t2 < tp.paths.length; t2++) {
                        var bk = backupOutput(tp.paths[t2], tag);
                        backups.push(bk.note);
                        if (bk.fail) skip = true;
                    }
                    if (skip) {
                        try { nu.remove(); } catch (e5b) {}
                        log("  건너뜀  " + label + " — " + backups.join(" / "));
                        continue;
                    }
                    try { if (nu.status !== RQItemStatus.QUEUED) nu.render = true; }
                    catch (e5) { log("  주의  " + label + " — 대기열 설정 실패: " + e5.message); }
                    newIdx.push({ obj: nu, tpl: tp, backups: backups });
                }

                proj.save();
                if (newIdx.length) {
                    progress("렌더 중… (" + newIdx.length + "개 항목)", 75);
                    closeProgress();
                    try { rq.render(); }
                    catch (e7) { log("  렌더 중 오류: " + e7.message); }
                }
            } finally {
                for (var p2 = 0; p2 < parked.length; p2++) { try { parked[p2].render = true; } catch (e8) {} }
            }

            for (var q1 = 0; q1 < newIdx.length; q1++) {
                var ent = newIdx[q1], st = "?";
                try { st = ent.obj.status === RQItemStatus.DONE ? "완료" : "미완료(상태 " + ent.obj.status + ")"; } catch (e9) {}
                var outs = [];
                for (var q2 = 0; q2 < ent.tpl.paths.length; q2++) {
                    var pth = ent.tpl.paths[q2];
                    outs.push(pth + (pth && !/\[#+\]/.test(pth) ? (new File(pth).exists ? "  [파일 있음]" : "  [파일 없음]") : ""));
                }
                rendered.push(st);
                log("  " + st + "  " + ent.tpl.comp.name + " · " + rqLabel(ent.tpl) + "\n        " + outs.join("\n        ") + "\n        " + ent.backups.join(" / "));
            }
            proj.save();
        } else if (tpls.length) {
            log("", "[렌더] 사용자가 렌더를 끔 — 렌더 큐는 그대로 둠");
        }
        if (compsNoHistory.length) {
            log("", "[렌더 이력 없는 컴프 — 출력 안 함, 필요하면 직접 렌더 큐에 추가]");
            for (var h1 = 0; h1 < compsNoHistory.length; h1++) log("  " + compsNoHistory[h1]);
        }

        // 8. FINAL QC 기록
        log("", "[요약]");
        var doneN = 0;
        for (var dn = 0; dn < rendered.length; dn++) if (rendered[dn] === "완료") doneN++;
        log("  교체 " + replaced.length + " / 실패 " + failed.length + " / 짝 없음 " + unmatched.length + " / 렌더 완료 " + doneN + "/" + rendered.length);
        var warnN = 0;
        for (var z = 0; z < replaced.length; z++) for (var z2 = 0; z2 < replaced[z].notes.length; z2++) if (replaced[z].notes[z2].indexOf("⚠") === 0) warnN++;
        log("  경고 " + warnN + "건 (⚠ 표시 확인)");
        log("  검수: 새 첫/아웃 프레임 스틸을 *" + "_pre" + suffix.replace(/^_+/, "") + ".* 백업과 나란히 비교해 LUT·노출·프레임 위치가 같은지 확인");

        var rp = splitExt(File.decode(newProj.name)).base;
        var repFile = new File(newProj.parent.fsName + "/" + rp + "_swap_report.txt");
        writeText(repFile, report.join(isWin ? "\r\n" : "\n"), true);
        closeProgress();
        if (trashRes) log("  휴지통 " + trashRes.trashed.length + "개" + (trashRes.left.length ? " / 못 옮김 " + trashRes.left.length + "개" : ""));
        alert("완료\n교체 " + replaced.length + "개, 실패 " + failed.length + "개, 짝 없음 " + unmatched.length + "개\n" +
            (trashRes ? "휴지통 " + trashRes.trashed.length + "개" + (trashRes.left.length ? " (못 옮김 " + trashRes.left.length + "개)" : "") + "\n" : "") +
            "렌더 완료 " + doneN + "/" + rendered.length +
            (compsNoHistory.length ? " (렌더 이력 없는 컴프 " + compsNoHistory.length + "개)" : "") +
            "\n경고 " + warnN + "건" + (warnN ? " — 보고서의 ⚠ 항목 확인" : "") +
            "\n\n작업 프로젝트: " + newProj.fsName + "\n보고서: " + repFile.fsName, SCRIPT_NAME);
        try { repFile.execute(); } catch (e10) {}
    }

    try { main(); }
    catch (err) {
        closeProgress();
        try { app.endUndoGroup(); } catch (e) {}
        alert("오류: " + err.message + (err.line ? " (line " + err.line + ")" : "") + "\n\n추가 변경을 멈췄습니다. 원본 .aep는 그대로입니다.", SCRIPT_NAME);
    }
})(this);
