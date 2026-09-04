/**
 * وعي التبويبات المتصفّحية — «فُتح من» و«لديك أيضاً».
 *
 * الأصيل تطبيق MDI: يفتح نوافذ ابنة ويعرف نوافذه، فقائمة النوافذ تُعيد المستخدم
 * إلى ما تركه. المتصفّح لا يعطي التطبيقَ هذه القائمة، فنبنيها بأنفسنا:
 *
 * 1. **المناولة (handoff):** `openInNewTab` يكتب سجلّاً محلياً بمُعرّف التبويب
 *    الفاتح واسم شاشته، ويُلحق رمزاً عابراً (`_ktab`) بالمسار الداخلي وحده.
 *    التبويب الجديد يلتقط الرمز **قبل إقلاع React** (`captureTabHandoffOnBoot`
 *    في `index.tsx`)، يقرأ السجلّ، يحذفه، وينظّف الرابط — فلا يبقى في العنوان
 *    أثرٌ يُشارَك أو يُحفَظ. لا نعتمد على `sessionStorage` ولا `window.name`:
 *    كلاهما يسقط مع `rel="noopener"` الذي نفتح به.
 *
 *    والرمز في **المرساة (`#`) لا في الاستعلام (`?`)** — وهذا ليس ذوقاً:
 *    مفتاح `Cache API` يشمل الاستعلام ويتجاهل المرساة، و`sw.ts` يخزّن كل تنقّل
 *    ناجح (`networkFirst`). فرمزٌ في الاستعلام — وهو UUID جديد لكل فتحة — كان
 *    يترك نسخةً دائمة من `index.html` في كاش المتصفّح **لكل تبويب يُفتح**، بلا
 *    سقف حتى النشرة التالية. مُقاسٌ في المتصفّح: ثلاث فتحات ⇒ 3 مدخلات
 *    بالاستعلام مقابل مدخل واحد بالمرساة. والمرساة لا تُرسَل للخادم أصلاً،
 *    فلا تلوّث سجلّات الوصول ولا كاش أي وسيط. **لا يظهر هذا في التطوير**:
 *    الـservice worker مُطفأ هناك (`devOptions: { enabled: false }`).
 * 2. **الحضور (presence):** كل تبويب يعلن نفسه على `BroadcastChannel` عند
 *    الإقلاع وعند تغيّر شاشته، ويودّع عند الإغلاق. بلا مؤقّتات ولا نبض دوري —
 *    مؤقّتٌ يعيد الرسم كل بضع ثوانٍ عطلٌ معروف في هذا المستودع.
 *
 * الدوالّ الصرفة (الرمز/الرابط/صلاحية السجلّ) أعلى الملف وتُختبر بلا متصفح؛
 * وما تحتها يلمس المتصفح ويحرسه `try/catch` — وعيُ التبويبات كماليّ، وسقوطه
 * لا يجوز أن يُسقط شاشة.
 */

/* ────────────────────────── دوالّ صرفة (قابلة للاختبار) ───────────────────── */

/** مفتاح المرساة العابر الذي يحمل رمز المناولة. يُزال فور قراءته. */
export const TAB_HANDOFF_PARAM = '_ktab';

/** مفتاح السجلّ في `localStorage`. */
export const TAB_HANDOFF_KEY_PREFIX = 'ktra.tabHandoff:';

/** عمر السجلّ: ما لم يُلتقط خلال دقيقة فالتبويب لم يُفتح، أو فُتح ثم أُغلق. */
export const TAB_HANDOFF_TTL_MS = 60_000;

export interface TabHandoff {
  /** مُعرّف التبويب الذي فتحنا منه. */
  openerId: string;
  /** اسم الشاشة التي كان عليها وقت الفتح («فواتير المبيعات»). */
  openerLabel: string;
  /** لحظة الفتح (ms). */
  at: number;
}

/**
 * مسارٌ داخليّ للتطبيق؟ الرمز يُلحق بهذه وحدها — إلحاقه برابط خارجي تسريبُ
 * معرّفٍ إلى طرف ثالث، وإلحاقه بـ`blob:` أو بمضيفٍ آخر يفسده أصلاً.
 */
export function isInternalPath(url: string): boolean {
  return typeof url === 'string' && url.startsWith('/') && !url.startsWith('//');
}

/**
 * يُلحق رمز المناولة **بمرساة** الرابط، آخرَ مقطعٍ فيها دائماً، مع الحفاظ على أي
 * مرساة قائمة قبله. الاستعلام يبقى كما هو حرفياً.
 */
export function withHandoffToken(url: string, token: string): string {
  if (!token || !isInternalPath(url)) return url;
  const hashAt = url.indexOf('#');
  const head = hashAt >= 0 ? url.slice(0, hashAt) : url;
  const existing = hashAt >= 0 ? url.slice(hashAt + 1) : '';
  const marker = `${TAB_HANDOFF_PARAM}=${encodeURIComponent(token)}`;
  return `${head}#${existing ? `${existing}&` : ''}${marker}`;
}

/** يقرأ الرمز من `location.hash`. */
export function readHandoffToken(hash: string): string | null {
  if (!hash) return null;
  const raw = hash.startsWith('#') ? hash.slice(1) : hash;
  const part = raw.split('&').find((p) => p.startsWith(`${TAB_HANDOFF_PARAM}=`));
  if (!part) return null;
  const token = decodeURIComponent(part.slice(TAB_HANDOFF_PARAM.length + 1));
  return token || null;
}

/**
 * نفس المرساة بلا مقطع المناولة — تُعيد ما كتبه المستدعي الأصلي حرفياً (لا
 * تطبيع `URLSearchParams`)، ونصّاً فارغاً حين لا يبقى شيء.
 */
export function hashWithoutHandoff(hash: string): string {
  if (!hash) return '';
  const raw = hash.startsWith('#') ? hash.slice(1) : hash;
  const rest = raw.split('&').filter((p) => !p.startsWith(`${TAB_HANDOFF_PARAM}=`));
  return rest.length ? `#${rest.join('&')}` : '';
}

/** سجلٌّ صالح: شكلُه سليم ولم يتقادم. */
export function isFreshHandoff(record: unknown, now: number): record is TabHandoff {
  if (!record || typeof record !== 'object') return false;
  const r = record as Partial<TabHandoff>;
  if (typeof r.openerId !== 'string' || typeof r.at !== 'number') return false;
  if (typeof r.openerLabel !== 'string') return false;
  return now - r.at >= 0 && now - r.at <= TAB_HANDOFF_TTL_MS;
}

/** أضيق واجهة تخزين تكفي المناولة — تُحقَن في الاختبار بلا متصفح. */
export interface HandoffStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function writeHandoff(store: HandoffStore, token: string, record: TabHandoff): void {
  store.setItem(TAB_HANDOFF_KEY_PREFIX + token, JSON.stringify(record));
}

/**
 * تبويبٌ حجبه مانع النوافذ لا يلتقط سجلّه أبداً، فيبقى في التخزين إلى الأبد.
 * كنسةٌ واحدة عند كل إقلاع تمنع التراكم الصامت.
 */
export function sweepStaleHandoffs(
  store: HandoffStore & { key?(i: number): string | null; length?: number },
  now: number,
): number {
  if (typeof store.key !== 'function' || typeof store.length !== 'number') return 0;
  const doomed: string[] = [];
  for (let i = 0; i < store.length; i += 1) {
    const key = store.key(i);
    if (!key || !key.startsWith(TAB_HANDOFF_KEY_PREFIX)) continue;
    const raw = store.getItem(key);
    let fresh = false;
    try {
      fresh = raw != null && isFreshHandoff(JSON.parse(raw), now);
    } catch { fresh = false; }
    if (!fresh) doomed.push(key);
  }
  doomed.forEach((key) => store.removeItem(key));
  return doomed.length;
}

/**
 * يقرأ السجلّ **ويحذفه** — المناولة تُستهلَك مرّة واحدة، فتحديثُ الصفحة لا
 * يُعيد إظهار المؤشّر (شرط المالك: مرّة لا متكرّراً).
 */
export function takeHandoff(store: HandoffStore, token: string, now: number): TabHandoff | null {
  const key = TAB_HANDOFF_KEY_PREFIX + token;
  const raw = store.getItem(key);
  store.removeItem(key);
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return isFreshHandoff(parsed, now) ? parsed : null;
  } catch {
    return null;
  }
}

/* ────────────────────────── الجانب المتصفّحي ─────────────────────────────── */

const PRESENCE_CHANNEL = 'ktra-tabs';

export interface LinkedTab {
  id: string;
  label: string;
  href: string;
}

interface Peer extends LinkedTab {
  openerId: string | null;
}

type PresenceMessage =
  | { t: 'hello'; peer: Peer }
  | { t: 'who'; from: string }
  | { t: 'bye'; id: string };

const randomId = (): string => {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch { /* متصفّح قديم أو سياق غير آمن */ }
  return `t${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
};

let selfId: string | null = null;
/** مُعرّف هذا التبويب — يُولَّد كسولاً كي لا يُنفَّذ شيء عند مجرّد الاستيراد. */
export function tabId(): string {
  if (selfId == null) selfId = randomId();
  return selfId;
}

let currentLabel = '';

const browserStore = (): HandoffStore | null => {
  try {
    if (typeof localStorage === 'undefined') return null;
    return localStorage;
  } catch {
    return null; // تصفّح خاص أو تخزين محجوب
  }
};

let incoming: TabHandoff | null = null;
let captured = false;

/**
 * يُنادى **مرّة واحدة قبل إقلاع React** (`index.tsx`): يلتقط رمز المناولة من
 * الرابط، يقرأ سجلّه، ثم ينظّف الرابط بـ`replaceState` — فلا يرى الموجّه
 * المعاملَ العابر أصلاً ولا يتسرّب إلى رابطٍ يُنسخ أو يُحفَظ.
 */
export function captureTabHandoffOnBoot(): void {
  if (captured) return;
  captured = true;
  try {
    if (typeof window === 'undefined') return;
    const store = browserStore();
    if (store) sweepStaleHandoffs(store as HandoffStore & Storage, Date.now());
    const token = readHandoffToken(window.location.hash);
    if (!token) return;
    if (store) incoming = takeHandoff(store, token, Date.now());
    const clean =
      window.location.pathname +
      window.location.search +
      hashWithoutHandoff(window.location.hash);
    window.history.replaceState(window.history.state, '', clean);
  } catch { /* الوعي كماليّ — لا يُسقط الإقلاع */ }
}

/** المناولة التي وصلت مع هذا التبويب، أو `null` إن فُتح مباشرةً. */
export function incomingHandoff(): TabHandoff | null {
  return incoming;
}

/* ── الحضور ── */

let channel: BroadcastChannel | null = null;
const peers = new Map<string, Peer>();
const listeners = new Set<(tabs: LinkedTab[]) => void>();
let lastSignature = '';

const selfPeer = (): Peer => ({
  id: tabId(),
  label: currentLabel,
  href: typeof window !== 'undefined' ? window.location.pathname + window.location.search : '',
  openerId: incoming?.openerId ?? null,
});

const post = (msg: PresenceMessage): void => {
  try { channel?.postMessage(msg); } catch { /* القناة مغلقة */ }
};

const announce = (): void => {
  if (channel) post({ t: 'hello', peer: selfPeer() });
};

/** يسجّل اسم الشاشة الحالية ويعلنه للتبويبات الأخرى. مصدره `VIEW_LABELS`. */
export function setCurrentTabLabel(label: string): void {
  if (label === currentLabel) return;
  currentLabel = label;
  announce();
}

export function getCurrentTabLabel(): string {
  return currentLabel;
}

/**
 * يُسجّل نيّة الفتح ويعيد الرابط محمّلاً بالرمز. يستدعيه `openInNewTab` وحده.
 */
export function prepareHandoffUrl(url: string): string {
  if (!isInternalPath(url)) return url;
  const store = browserStore();
  if (!store) return url;
  const token = randomId();
  try {
    writeHandoff(store, token, { openerId: tabId(), openerLabel: currentLabel, at: Date.now() });
  } catch {
    return url; // حصّة التخزين ممتلئة — نفتح بلا وعي بدل أن نمنع الفتح
  }
  return withHandoffToken(url, token);
}

/**
 * التبويبات **المرتبطة** بهذا: الذي فتحنا منه، ومَن فتحناه نحن. تبويبٌ ثالث
 * فتحه المستخدم بنفسه ليس من شأن هذا التلميح.
 */
const linkedTabs = (): LinkedTab[] => {
  const me = tabId();
  const openerId = incoming?.openerId ?? null;
  return [...peers.values()]
    .filter((p) => p.id !== me && (p.id === openerId || p.openerId === me))
    .map(({ id, label, href }) => ({ id, label, href }));
};

const notify = (): void => {
  const tabs = linkedTabs();
  const signature = tabs.map((t) => `${t.id}|${t.label}`).join('~');
  if (signature === lastSignature) return; // بلا إعادة رسم لتغيّرٍ لم يحدث
  lastSignature = signature;
  listeners.forEach((cb) => cb(tabs));
};

const openChannel = (): void => {
  if (channel || typeof BroadcastChannel === 'undefined') return;
  try {
    channel = new BroadcastChannel(PRESENCE_CHANNEL);
  } catch {
    return;
  }
  channel.onmessage = (event: MessageEvent<PresenceMessage>) => {
    const msg = event.data;
    if (!msg) return;
    if (msg.t === 'hello') {
      if (msg.peer.id === tabId()) return;
      peers.set(msg.peer.id, msg.peer);
      notify();
    } else if (msg.t === 'bye') {
      if (peers.delete(msg.id)) notify();
    } else if (msg.t === 'who' && msg.from !== tabId()) {
      announce();
    }
  };
  window.addEventListener('pagehide', () => post({ t: 'bye', id: tabId() }));
  post({ t: 'who', from: tabId() });
  announce();
};

/**
 * يشترك في قائمة التبويبات المرتبطة الحيّة. يُعيد دالّة إلغاء الاشتراك.
 * القناة تبقى مفتوحة ما بقي مشترك — لا فتحَ وإغلاقَ مع كل رسمة.
 */
export function subscribeLinkedTabs(cb: (tabs: LinkedTab[]) => void): () => void {
  listeners.add(cb);
  openChannel();
  cb(linkedTabs());
  return () => { listeners.delete(cb); };
}

/**
 * يفتح قناة الحضور بلا اشتراكٍ لعرض — لمستهلكٍ يحتاج فقط معرفة «هل هذا
 * التبويب حيّ؟» (issue #119: إنذار الكتابة فوق مسودّة مستندٍ مفتوحٍ في تبويبٍ
 * آخر) لا قائمة التبويبات المرتبطة. يُعيد دالّة إغلاق الاشتراك — القناة نفسها
 * تبقى مفتوحة (مُشتركة مع كل مستهلك آخر) ما دام مستهلكٌ واحد على الأقل حيّاً.
 */
export function subscribeTabPresence(): () => void {
  const noop = () => {};
  listeners.add(noop);
  openChannel();
  return () => { listeners.delete(noop); };
}

/**
 * تبويبٌ **حيّ الآن** بمعرّفه — بلا تصفية «المرتبطة» (خلاف `linkedTabs`، وهو
 * ما يلزم إنذار الكتابة المتزامنة: أيّ تبويبٍ آخر يفتح نفس المستند، لا فقط ما
 * فتحناه نحن أو فتحنا منه). يعتمد على `peers` وهي لا تُملأ إلا بعد فتح القناة
 * (`subscribeTabPresence`/`subscribeLinkedTabs`) وتبادل `hello`/`who` —
 * فحصٌ مبكرٌ جداً بعد الفتح قد يُعطي سلباً كاذباً بلا ضمان، وهذا مقبول هنا:
 * تنبيهٌ ناقصٌ أهون من قناةٍ مفتوحة بلا مستهلك.
 */
export function isTabIdLive(id: string): boolean {
  return peers.has(id);
}
