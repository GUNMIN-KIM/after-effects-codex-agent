// Wraps gemini-neon.html (the Artifact source, which has no document skeleton)
// into index.html, a complete page you can open locally or host anywhere.
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const body = readFileSync(join(here, 'gemini-neon.html'), 'utf8');
const page = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="dark">
</head>
<body>
${body}
</body>
</html>
`;
writeFileSync(join(here, 'index.html'), page);
console.log('index.html written (' + page.length + ' bytes)');
