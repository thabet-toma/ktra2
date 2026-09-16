/** الأحرفُ الأولى من اسمٍ عربيٍّ أو لاتينيّ — مصدرٌ واحدٌ لكلّ صورةٍ رمزيّة.
 *
 *  كانت خمسُ نسخٍ من هذا المنطق في `components/platform/` تأخذ أوّلَ حرفٍ من
 *  أوّل كلمتين حرفيّاً، فتُخرج لـ«عمر الشريف» **عا** ولـ«رنا الخطيب» **را**:
 *  أداةُ التعريف «ال» ليست حرفَ الاسم. رآه المالكُ في اللقطة، ولا بوّابةَ
 *  تصيّر مكوّناً فتمسكه — ولذلك صارت دالّةً خالصةً يحرسها `npm test`.
 */

/** «عبد» و«أبو» و«بن» لا تقوم أسماءً وحدَها: تُدمج مع ما بعدها في رمزٍ واحد
 *  حرفُه حرفُها، فـ«لينا عبد الله» تُعطي **لع** لا **لع**بد مقطوعةً ولا **لا**. */
const COMPOUND_PARTICLES = new Set(["عبد", "أبو", "ابو", "بن", "ابن", "بنت", "آل"]);

/** «الله» تبدأ بـ«ال» ولا تُنزع منها: النزعُ الأعمى يُحيلها «له». */
const NEVER_STRIPPED = new Set(["الله", "الرحمن", "الرحيم"]);

function stripArabicArticle(word: string): string {
  if (NEVER_STRIPPED.has(word)) return word;
  if (word.length > 3 && word.startsWith("ال")) return word.slice(2);
  return word;
}

export function ccInitials(name: string, fallback = "؟"): string {
  const words = String(name ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return fallback;

  // الدمجُ أوّلاً: أداةُ التركيب تبتلع تاليَها فيصير الرمزان اسمين حقيقيّين.
  const tokens: string[] = [];
  for (let i = 0; i < words.length; i += 1) {
    if (COMPOUND_PARTICLES.has(words[i]) && i + 1 < words.length) {
      tokens.push(`${words[i]} ${words[i + 1]}`);
      i += 1;
    } else {
      tokens.push(stripArabicArticle(words[i]));
    }
  }

  if (tokens.length === 1) return tokens[0].slice(0, 2);
  return tokens[0][0] + tokens[1][0];
}

export default ccInitials;
