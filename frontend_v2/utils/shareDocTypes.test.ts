/**
 * حارسُ تكافؤٍ بين `ShareDocType` في الواجهة و`DOC_TYPES` في الخادم.
 *
 * **لماذا اختبارٌ نصّي لا `tsc`:** لا `@types/react` في هذا المستودع، فمُدقّق
 * الأنواع **لا يفحص خصائص JSX إطلاقاً** — و`docType` تُمرَّر خاصيةً في كل نقطة
 * التحام. وقد وقع ذلك فعلاً في هذا العمل: أُضيفت سبعةُ أنواع إلى الخادم
 * وأزرارُها إلى سبع شاشات، و`tsc` بقي **أخضر** بينما الاتحاد ينقصه سبع قيم —
 * نوعٌ يكذب بلا صوت، ولا بناءٌ ولا مُدقّقٌ يمسكه. هذا الملف يقرأ المصدرين
 * نصّاً ويقارن المجموعتين، فالانحراف يُمسَك في ثوانٍ لا في مراجعةٍ بصرية.
 */
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

function frontendTypes(): Set<string> {
  const src = readFileSync(
    join(ROOT, "frontend_v2", "services", "docShareApi.ts"),
    "utf8",
  );
  const block = src.slice(src.indexOf("export type ShareDocType"));
  const decl = block.slice(0, block.indexOf(";"));
  return new Set([...decl.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]));
}

function serverTypes(): Set<string> {
  const dir = join(ROOT, "docshare", "documents");
  const found = new Set<string>();
  for (const file of readdirSync(dir).filter((f) => f.endsWith("_docs.py"))) {
    const src = readFileSync(join(dir, file), "utf8");
    const registry = src.slice(src.lastIndexOf("DOC_TYPES = {"));
    for (const m of registry.matchAll(/^ {4}"([a-z_]+)": \{/gm)) found.add(m[1]);
  }
  return found;
}

test("كل نوع مسجَّل في الخادم موجود في اتحاد ShareDocType", () => {
  const server = serverTypes();
  const front = frontendTypes();
  // حارسٌ للحارس: تحليلٌ نصّي انكسر يُرجع مجموعةً فارغة فيمرّ الاختبار كاذباً.
  assert.ok(
    server.size >= 14,
    `قُرئ ${server.size} نوعاً من الخادم — التحليل النصّي انكسر`,
  );
  const missing = [...server].filter((t) => !front.has(t));
  assert.deepEqual(missing, [], `ينقص اتحاد ShareDocType: ${missing.join(", ")}`);
});

test("ولا نوع في الواجهة بلا مقابلٍ في الخادم", () => {
  const server = serverTypes();
  const extra = [...frontendTypes()].filter((t) => !server.has(t));
  assert.deepEqual(extra, [], `أنواع في الواجهة بلا خادم: ${extra.join(", ")}`);
});
