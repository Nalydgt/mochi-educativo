import ts from "typescript";
import fs from "node:fs";
const cfg = ts.readConfigFile("tsconfig.json", ts.sys.readFile);
const parsed = ts.parseJsonConfigFileContent(cfg.config, ts.sys, ".");
const p = ts.createProgram(parsed.fileNames, parsed.options);
const groups = new Map();
for (const d of ts.getPreEmitDiagnostics(p))
  if (
    d.code === 4111 &&
    d.file &&
    d.start !== undefined &&
    /[/\\](education)[/\\]/.test(d.file.fileName)
  ) {
    const file = d.file.fileName;
    let changes = groups.get(file);
    if (!changes) groups.set(file, (changes = []));
    const n = d.file.text.slice(d.start, d.start + d.length);
    const optional = d.file.text.slice(d.start - 2, d.start) === "?.";
    changes.push({
      start: d.start - (optional ? 0 : 1),
      end: d.start + d.length,
      text: `['${n}']`,
    });
  }
for (const [file, changes] of groups) {
  let text = fs.readFileSync(file, "utf8");
  for (const c of changes.sort((a, b) => b.start - a.start))
    text = text.slice(0, c.start) + c.text + text.slice(c.end);
  fs.writeFileSync(file, text);
}
console.log(`Fixed index access in ${groups.size} new files`);
