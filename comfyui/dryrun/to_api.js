// usage: node to_api.js workflow.json out_api.json
const fs = require('fs');
const { chromium } = require('playwright');
(async () => {
  const [wfPath, outPath] = process.argv.slice(2);
  const exe = process.env.CHROMIUM_PATH || (fs.existsSync('/opt/pw-browsers/chromium-1194/chrome-linux/chrome') ? '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' : undefined);
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const page = await browser.newPage();
  const logs = [];
  page.on('console', m => { if (['error', 'warning'].includes(m.type())) logs.push(`[${m.type()}] ${m.text()}`); });
  page.on('pageerror', e => logs.push(`[pageerror] ${e.message}`));
  await page.goto(process.env.COMFY_URL || 'http://127.0.0.1:8188', { waitUntil: 'networkidle' });
  await page.waitForFunction(() => window.app && window.app.graph && window.app.graph.nodes !== undefined, null, { timeout: 60000 });
  const wf = JSON.parse(fs.readFileSync(wfPath, 'utf8'));
  const res = await page.evaluate(async (wf) => {
    const out = { warnings: [] };
    try {
      await window.app.loadGraphData(wf, true, true, 'dryrun');
      const g = window.app.graph;
      out.loaded_nodes = g.nodes.length;
      out.missing = g.nodes.filter(n => n.has_errors || n.constructor?.type === undefined || n.type === undefined).map(n => n.type);
      const p = await window.app.graphToPrompt();
      out.output = p.output;
    } catch (e) { out.error = String(e && e.stack || e); }
    return out;
  }, wf);
  // collect visible dialogs text (missing nodes / models)
  const dialogs = await page.$$eval('.p-dialog', ds => ds.map(d => d.innerText.slice(0, 800)));
  res.dialogs = dialogs;
  res.console = logs.slice(0, 60);
  fs.writeFileSync(outPath, JSON.stringify(res, null, 1));
  await browser.close();
  console.log(JSON.stringify({ nodes: res.loaded_nodes, api_nodes: res.output ? Object.keys(res.output).length : 0, error: res.error, dialogs: res.dialogs, console: res.console.slice(0, 15) }, null, 1));
})();
