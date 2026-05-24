/**
 * Density Audit Script — P-G-13
 *
 * Checks every form component for:
 * 1. File size > 400 lines (potential density issue)
 * 2. Use of CollapsibleSection (should be tabs instead)
 * 3. Use of `space-y-` or `p-` large padding classes
 * 4. Multiple sections in form (indicates vertical stacking)
 *
 * Usage: node scripts/density-audit.js [--fix] [--ci]
 */

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const COMPONENTS = path.join(ROOT, "components");

const SUSPECT_PATTERNS = [
  { name: "CollapsibleSection import", regex: /CollapsibleSection/g },
  { name: "large padding (p-6|p-8|p-10)", regex: /p-[6-9]|p-10/g },
  { name: "large spacing (space-y-4|space-y-6)", regex: /space-y-[4-9]/g },
  { name: "vertical stack sections", regex: /<section|<div className="[^"]*mb-[4-9]/g },
  { name: "any type usage", regex: /: any/g },
];

function walk(dir, results = []) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory() && !e.name.startsWith(".") && e.name !== "node_modules") walk(p, results);
    else if (e.isFile() && /\.(tsx|ts)$/.test(e.name)) results.push(p);
  }
  return results;
}

function audit() {
  const files = walk(COMPONENTS);
  let issues = [];

  for (const f of files) {
    const content = fs.readFileSync(f, "utf-8");
    const lines = content.split("\n").length;

    if (lines > 400) {
      issues.push({ file: path.relative(ROOT, f), type: "size", detail: `${lines} lines (>400)` });
    }

    for (const p of SUSPECT_PATTERNS) {
      const matches = content.match(p.regex);
      if (matches) {
        issues.push({ file: path.relative(ROOT, f), type: p.name, detail: `${matches.length} match(es)` });
      }
    }
  }

  return issues;
}

function main() {
  const isCi = process.argv.includes("--ci");
  const issues = audit();

  if (issues.length === 0) {
    console.log("✓ Density audit passed — no issues found.");
    process.exit(0);
  }

  // Group by file
  const grouped = {};
  for (const i of issues) {
    if (!grouped[i.file]) grouped[i.file] = [];
    grouped[i.file].push(i);
  }

  console.log(`\n⚠ Density audit found ${issues.length} issue(s) in ${Object.keys(grouped).length} file(s):\n`);
  for (const [file, fileIssues] of Object.entries(grouped).sort()) {
    console.log(`  ${file}:`);
    for (const i of fileIssues) {
      console.log(`    - ${i.type}: ${i.detail}`);
    }
    console.log();
  }

  if (isCi) {
    console.log("❌ CI density guard: FAILED — fix issues before merging.");
    process.exit(1);
  }
}

main();
