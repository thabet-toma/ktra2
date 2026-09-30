import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { PUBLIC_PAGES, SITE_ORIGIN, findPublicPage } from "../constants/publicPages.ts";
import {
  applyPageHead,
  buildSitemapXml,
  isUnknownAnonymousPath,
  pathRoot,
  prerenderFilePath,
  resolveLastmod,
} from "./seoHead.ts";

const TEMPLATE = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const ROBOTS = readFileSync(new URL("../public/robots.txt", import.meta.url), "utf8");
const aboutUs = findPublicPage("/about-us")!;

test("الـconfig: canonical مطلق = الأصل + المسار، بلا شرطة مائلة في آخره، وبلا تكرار", () => {
  assert.equal(PUBLIC_PAGES.length, 5);
  for (const page of PUBLIC_PAGES) {
    assert.equal(page.canonical, page.path === "/" ? SITE_ORIGIN : SITE_ORIGIN + page.path);
    assert.ok(!page.canonical.endsWith("/"), page.canonical);
    assert.ok(page.title && page.description, page.path);
    assert.doesNotThrow(() => readFileSync(new URL(`../${page.component}`, import.meta.url)), page.component);
  }
  assert.equal(new Set(PUBLIC_PAGES.map((p) => p.path)).size, PUBLIC_PAGES.length);
  assert.equal(new Set(PUBLIC_PAGES.map((p) => p.title)).size, PUBLIC_PAGES.length);
});

test("findPublicPage يتجاهل الشرطة الأخيرة ويرفض ما ليس عاماً", () => {
  assert.equal(findPublicPage("/about-us/")?.path, "/about-us");
  assert.equal(findPublicPage("")?.path, "/");
  assert.equal(findPublicPage("/dashboard"), null);
  assert.equal(findPublicPage("/store/ktra"), null);
});

test("applyPageHead على قالب index.html الحقيقي: الوسوم الأربعة ومعاينة الروابط للصفحة نفسها", () => {
  const html = applyPageHead(TEMPLATE, aboutUs);
  assert.match(html, /<title[^>]*>من نحن — نظام K\.T\.R\.A[^<]*<\/title>/);
  assert.match(html, /<link[^>]*rel="canonical"[^>]*href="https:\/\/ktra-pro\.tech\/about-us"/);
  assert.match(html, /property="og:url"[^>]*content="https:\/\/ktra-pro\.tech\/about-us"/);
  assert.match(html, new RegExp(`name="description"\\s+content="${aboutUs.description}"`));
  assert.match(html, new RegExp(`property="og:title"\\s+content="${aboutUs.title.replace(/\./g, "\\.")}"`));
  assert.match(html, new RegExp(`name="twitter:description"\\s+content="${aboutUs.description}"`));
  // لا يبقى أثرٌ لعنوان الصفحة الرئيسية في الـcanonical أو og:url.
  assert.doesNotMatch(html, /href="https:\/\/ktra-pro\.tech\/"/);
  assert.doesNotMatch(html, /og:url"[^>]*content="https:\/\/ktra-pro\.tech\/"/);
  // وسوم الرأس الواحدة تبقى واحدة، وبقيّة القالب (السكربت والجذر) لم تُمسّ.
  assert.equal(html.match(/<title\b/g)?.length, 1);
  assert.equal(html.match(/rel="canonical"/g)?.length, 1);
  assert.ok(html.includes('<div id="root"></div>'));
  assert.ok(html.includes('<script type="module" src="/index.tsx"></script>'));
});

test("applyPageHead يهرّب القيم ولا يفسّر $ نمطَ استبدال", () => {
  const html = applyPageHead(TEMPLATE, { ...aboutUs, title: 'A & B "$&" <x>', description: "$1 وصف" });
  assert.match(html, /<title[^>]*>A &amp; B &quot;\$&amp;&quot; &lt;x&gt;<\/title>/);
  assert.match(html, /name="description"\s+content="\$1 وصف"/);
});

test("applyPageHead يُسقط البناء إن غاب وسم من القالب", () => {
  assert.throws(() => applyPageHead(TEMPLATE.replace(/<link rel="canonical"[^>]*>/, ""), aboutUs), /canonical/);
  assert.throws(() => applyPageHead(TEMPLATE.replace(/<meta property="og:url"[^>]*>/, ""), aboutUs), /og:url/);
  assert.throws(() => applyPageHead("<html></html>", aboutUs), /title/);
});

test("prerenderFilePath", () => {
  assert.equal(prerenderFilePath("/"), "index.html");
  assert.equal(prerenderFilePath("/about-us"), "about-us/index.html");
  assert.equal(prerenderFilePath("/store/"), "store/index.html");
});

test("resolveLastmod: تاريخ الـcommit إن صلح، وإلا يوم البناء", () => {
  const build = new Date("2026-09-30T23:30:00Z");
  assert.equal(resolveLastmod("2026-08-14\n", build), "2026-08-14");
  assert.equal(resolveLastmod("", build), "2026-09-30");
  assert.equal(resolveLastmod(null, build), "2026-09-30");
  assert.equal(resolveLastmod("fatal: not a git repository", build), "2026-09-30");
});

test("buildSitemapXml: loc وlastmod فقط، وloc مطابق حرفياً للـcanonical", () => {
  const xml = buildSitemapXml(PUBLIC_PAGES.map((p) => ({ loc: p.canonical, lastmod: "2026-09-01" })));
  assert.ok(xml.startsWith('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'));
  const locs = [...xml.matchAll(/<loc>([^<]*)<\/loc>/g)].map((m) => m[1]);
  assert.deepEqual(locs, PUBLIC_PAGES.map((p) => p.canonical));
  assert.equal(xml.match(/<lastmod>2026-09-01<\/lastmod>/g)?.length, PUBLIC_PAGES.length);
  assert.doesNotMatch(xml, /changefreq|priority/);
  assert.throws(() => buildSitemapXml([{ loc: SITE_ORIGIN, lastmod: "30/09/2026" }]), /lastmod/);
});

test("robots.txt متّسق مع القائمة: كل صفحة عامة مسموحة ولا يحجبها Disallow، والخريطة مذكورة", () => {
  const lines = ROBOTS.split(/\r?\n/).map((l) => l.trim());
  const allows = new Set(lines.filter((l) => l.startsWith("Allow:")).map((l) => l.slice(6).trim()));
  const disallows = lines.filter((l) => l.startsWith("Disallow:")).map((l) => l.slice(9).trim()).filter(Boolean);
  for (const page of PUBLIC_PAGES) {
    assert.ok(allows.has(page.path), `Allow: ${page.path}`);
    assert.ok(!disallows.some((d) => page.path.startsWith(d)), `Disallow يحجب ${page.path}`);
  }
  assert.ok(lines.includes(`Sitemap: ${SITE_ORIGIN}/sitemap.xml`));
});

test("isUnknownAnonymousPath: 404 لما ليس صفحة عامة ولا جذراً داخلياً", () => {
  const roots = new Set(["about-us", "contact", "gallery", "sales", "accounting"]);
  assert.equal(isUnknownAnonymousPath("/", roots), false);
  assert.equal(isUnknownAnonymousPath("", roots), false);
  assert.equal(isUnknownAnonymousPath("/about-us/", roots), false);
  assert.equal(isUnknownAnonymousPath("/sales/invoices/5", roots), false);
  assert.equal(isUnknownAnonymousPath("/no-such-page", roots), true);
  assert.equal(isUnknownAnonymousPath("/salesx", roots), true);
  assert.equal(pathRoot("/accounting/coa"), "accounting");
  assert.equal(pathRoot("/"), "");
});
