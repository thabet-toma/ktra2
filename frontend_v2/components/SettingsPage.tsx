/**
 * N7-T7 — SettingsPage — Kit form sections
 */
import React, { useState, useEffect } from 'react';
import { User, AppView } from '../types';
import { updateUserInDb } from '../services/firestoreService';
import { changeUserPassword } from '../services/authService';
import {
    SHORTCUTABLE_VIEWS,
    getQuickShortcuts,
    setQuickShortcuts,
} from '../utils/quickShortcuts';
import { usePriceVisibility } from '../contexts/PriceVisibilityContext';
import { useAppearance, FONT_SCALE_OPTIONS, FONT_FAMILY_OPTIONS } from '../contexts/AppearanceContext';
import { useSessionSettings, IDLE_MIN_MINUTES, IDLE_MAX_MINUTES } from '../contexts/SessionSettingsContext';
import { getSkin, setSkin, UiSkin } from '../styles/skin';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../contexts/ConfirmContext';
import { useSimpleUi } from '../hooks/useSimpleUi';
import { humanizeThrown } from '../utils/drfError';
import { formatDateTimeValue } from '../utils/formatDate';
import {
    listLoginDevices,
    evictLoginDevice,
    evictOtherLoginDevices,
    setPrimaryLoginDevice,
    renameLoginDevice,
    type LoginDevice,
} from '../services/loginDevicesApi';

interface SettingsPageProps {
    user: User;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({ user }) => {
    const toast = useToast();
    const confirm = useConfirm();
    const { show: showAdv } = useSimpleUi();
    const [profileForm, setProfileForm] = useState({
        name: user.name,
        phone: user.phone || '',
        address: user.address || '',
        educationLevel: user.educationLevel || '',
        experienceDescription: user.experienceDescription || '',
    });
    const [resumeFile, setResumeFile] = useState<File | null>(null);
    const [passwordForm, setPasswordForm] = useState({ oldPassword: '', newPassword: '', confirmPassword: '' });
    const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
    const [loadingProfile, setLoadingProfile] = useState(false);
    const [loadingPassword, setLoadingPassword] = useState(false);
    // task16 D14: اختصارات الوصول السريع المختارة
    const [quickShortcuts, setQuickShortcutsState] = useState<AppView[]>(() => getQuickShortcuts());
    // خصوصية عرض الأسعار/الأرباح (زر العين) — مصدر واحد عالمي في PriceVisibilityContext.
    const { showToggle, setShowToggle, defaultVisible, setDefaultVisible } = usePriceVisibility();
    // المظهر — حجم الخط ونوعه (تفضيل عام محلي في AppearanceContext).
    const { fontScale, setFontScale, fontFamily, setFontFamily } = useAppearance();
    // مهلة الخمول قبل إنهاء الجلسة (per-company عبر SessionSettings).
    const { idleTimeoutMinutes, setIdleTimeoutMinutes } = useSessionSettings();
    const [idleInput, setIdleInput] = useState<string>(() => String(idleTimeoutMinutes));
    const [uiSkin, setUiSkin] = useState<UiSkin>(() => getSkin());

    // ── أجهزة الدخول (ISSUE #168) ────────────────────────────────────────────
    const [devices, setDevices] = useState<LoginDevice[]>([]);
    // نصُّ حارس الجهاز الأساسيّ حين يكون هذا الجهاز ثانويّاً — تفسيرٌ لا فراغ.
    const [devicesGuard, setDevicesGuard] = useState<string | null>(null);
    const [devicesInvitation, setDevicesInvitation] = useState<string | null>(null);
    const [primaryPrompt, setPrimaryPrompt] = useState(false);
    const [primaryPassword, setPrimaryPassword] = useState('');
    const [renamingId, setRenamingId] = useState<number | null>(null);
    const [renameValue, setRenameValue] = useState('');

    const loadDevices = React.useCallback(async () => {
        try {
            const res = await listLoginDevices();
            if (res.kind === 'primary_required') {
                setDevicesGuard(res.detail);
                setDevices([]);
                setDevicesInvitation(null);
                return;
            }
            setDevicesGuard(null);
            setDevices(res.devices);
            setDevicesInvitation(res.has_primary ? null : res.primary_invitation);
        } catch (e) {
            toast(humanizeThrown(e, 'تعذّر جلب أجهزة الدخول.'), 'error');
        }
    }, [toast]);

    useEffect(() => { void loadDevices(); }, [loadDevices]);

    const handleEvictDevice = async (d: LoginDevice) => {
        if (!(await confirm({
            title: 'إنهاء جهاز',
            message: `سيتوقّف «${d.name}» عن العمل عند أوّل طلبٍ يرسله. متابعة؟`,
            confirmText: 'إنهاء',
        }))) return;
        try {
            toast(await evictLoginDevice(d.id), 'success');
            await loadDevices();
        } catch (e) {
            toast(humanizeThrown(e, 'تعذّر إنهاء الجهاز.'), 'error');
        }
    };

    const handleEvictOthers = async () => {
        if (!(await confirm({
            title: 'إخراج كل الأجهزة الأخرى',
            message: 'ستتوقّف كلُّ أجهزتك الأخرى ويبقى هذا الجهاز وحده. متابعة؟',
            confirmText: 'إخراج',
        }))) return;
        try {
            const n = await evictOtherLoginDevices();
            toast(n > 0 ? `تم إنهاء ${n} من الأجهزة الأخرى.` : 'لا أجهزة أخرى لإنهائها.', 'success');
            await loadDevices();
        } catch (e) {
            toast(humanizeThrown(e, 'تعذّر إنهاء الأجهزة الأخرى.'), 'error');
        }
    };

    const handleSetPrimary = async () => {
        try {
            await setPrimaryLoginDevice(primaryPassword);
            setPrimaryPrompt(false);
            setPrimaryPassword('');
            toast('تم تعيين هذا الجهاز أساسيّاً.', 'success');
            await loadDevices();
        } catch (e) {
            toast(humanizeThrown(e, 'تعذّر تعيين الجهاز الأساسيّ.'), 'error');
        }
    };

    // التسميةُ تحريرٌ داخل البطاقة: لا `window.prompt`، ولا حوارَ مخترَعٌ لهذه
    // الشاشة وحدها (المستودع فيه `useConfirm` ولا مقابلَ له للإدخال).
    const commitRename = async (id: number) => {
        try {
            await renameLoginDevice(id, renameValue.trim());
            setRenamingId(null);
            setRenameValue('');
            await loadDevices();
        } catch (e) {
            toast(humanizeThrown(e, 'تعذّرت إعادة التسمية.'), 'error');
        }
    };

    // مزامنة حقل الإدخال مع القيمة القادمة من الخادم بعد المزامنة الأوّلية.
    useEffect(() => { setIdleInput(String(idleTimeoutMinutes)); }, [idleTimeoutMinutes]);

    // اعتماد قيمة الحقل: يقصّها ضمن النطاق ويحفظها خادمياً؛ الفارغ/غير الرقمي يُعاد للحالي.
    const commitIdleTimeout = () => {
        const n = Number(idleInput);
        if (!Number.isFinite(n)) { setIdleInput(String(idleTimeoutMinutes)); return; }
        setIdleTimeoutMinutes(n);
    };

    const toggleShortcut = (view: AppView) => {
        setQuickShortcutsState((prev) => {
            const next = prev.includes(view) ? prev.filter((v) => v !== view) : [...prev, view];
            setQuickShortcuts(next);
            return next;
        });
    };

    useEffect(() => {
        setProfileForm({
            name: user.name, phone: user.phone || '', address: user.address || '',
            educationLevel: user.educationLevel || '', experienceDescription: user.experienceDescription || '',
        });
    }, [user]);

    useEffect(() => {
        const handleSkinChange = (event: Event) => {
            setUiSkin((event as CustomEvent<UiSkin>).detail);
        };

        window.addEventListener('ktra:skin', handleSkinChange);
        return () => window.removeEventListener('ktra:skin', handleSkinChange);
    }, []);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (file.size > 800 * 1024) { setMessage({ type: 'error', text: 'حجم الملف كبير جداً. الحد الأقصى 800 كيلوبايت.' }); return; }
        setResumeFile(file);
        setMessage(null);
    };

    const convertFileToBase64 = (file: File): Promise<string> =>
        new Promise((res, rej) => { const r = new FileReader(); r.readAsDataURL(file); r.onload = () => res(r.result as string); r.onerror = rej; });

    const handleProfileUpdate = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoadingProfile(true); setMessage(null);
        try {
            const updates: any = { id: user.id, ...profileForm };
            if (resumeFile) updates.resumeData = { name: resumeFile.name, type: resumeFile.type, data: await convertFileToBase64(resumeFile) };
            await updateUserInDb(updates);
            setMessage({ type: 'success', text: 'تم تحديث البيانات الشخصية بنجاح.' });
            setResumeFile(null);
        } catch { setMessage({ type: 'error', text: 'حدث خطأ أثناء تحديث البيانات.' }); }
        finally { setLoadingProfile(false); }
    };

    const handlePasswordChange = async (e: React.FormEvent) => {
        e.preventDefault(); setMessage(null);
        if (passwordForm.newPassword !== passwordForm.confirmPassword) { setMessage({ type: 'error', text: 'كلمة المرور الجديدة غير متطابقة.' }); return; }
        if (passwordForm.newPassword.length < 6) { setMessage({ type: 'error', text: 'كلمة المرور يجب أن تكون 6 خانات على الأقل.' }); return; }
        setLoadingPassword(true);
        try {
            await changeUserPassword(passwordForm.oldPassword, passwordForm.newPassword);
            setMessage({ type: 'success', text: 'تم تغيير كلمة المرور بنجاح.' });
            setPasswordForm({ oldPassword: '', newPassword: '', confirmPassword: '' });
        } catch (err: any) {
            if (err.code === 'auth/invalid-credential' || err.code === 'auth/wrong-password') setMessage({ type: 'error', text: 'كلمة المرور الحالية غير صحيحة.' });
            else setMessage({ type: 'error', text: 'حدث خطأ. يرجى التأكد من كلمة المرور.' });
        } finally { setLoadingPassword(false); }
    };

    const sectionStyle: React.CSSProperties = { border: '1px solid var(--ktra-border)', borderRadius: 6, padding: '14px 18px', marginBottom: 14 };
    const sectionTitleStyle: React.CSSProperties = { fontSize: 'var(--ktra-fs-title, 14px)', fontWeight: 700, color: 'var(--ktra-ink)', marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid var(--ktra-border)' };
    const fieldStyle: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4 };
    const labelStyle: React.CSSProperties = { fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-ink)', fontWeight: 500 };
    const gridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 };

    return (
        <div dir="rtl" style={{ padding: '8px 12px', maxWidth: 780 }}>
            {/* العنوان */}
            <div style={{ paddingBottom: 8, borderBottom: '1px solid var(--ktra-border)', marginBottom: 14 }}>
                <strong style={{ fontSize: 'var(--ktra-fs-title, 14px)', color: 'var(--ktra-ink)' }}>الإعدادات</strong>
            </div>

            {/* رسالة الحالة */}
            {message && (
                <div style={{ padding: '8px 12px', borderRadius: 6, marginBottom: 12, fontSize: 'var(--ktra-fs-sm)', background: message.type === 'success' ? 'rgba(38,115,70,0.08)' : 'rgba(204,0,0,0.08)', color: message.type === 'success' ? 'var(--ktra-ok, #267346)' : 'var(--ktra-danger, #c00)', border: `1px solid ${message.type === 'success' ? 'var(--ktra-ok, #267346)' : 'var(--ktra-danger, #c00)'}` }}>
                    {message.text}
                </div>
            )}

            {/* المعلومات الشخصية والمهنية */}
            <form onSubmit={handleProfileUpdate}>
                <div style={sectionStyle}>
                    <div style={sectionTitleStyle}>المعلومات الشخصية والمهنية</div>
                    <div style={gridStyle}>
                        <div style={fieldStyle}>
                            <label style={labelStyle}>الاسم الكامل</label>
                            <input className="ktra-input" required value={profileForm.name} onChange={e => setProfileForm({ ...profileForm, name: e.target.value })} />
                        </div>
                        <div style={fieldStyle}>
                            <label style={labelStyle}>البريد الإلكتروني (للقراءة فقط)</label>
                            <input className="ktra-input" type="email" value={user.email} disabled style={{ opacity: 0.6, cursor: 'not-allowed' }} />
                        </div>
                        <div style={fieldStyle}>
                            <label style={labelStyle}>رقم الهاتف</label>
                            <input className="ktra-input" type="tel" value={profileForm.phone} onChange={e => setProfileForm({ ...profileForm, phone: e.target.value })} />
                        </div>
                        <div style={fieldStyle}>
                            <label style={labelStyle}>العنوان</label>
                            <input className="ktra-input" value={profileForm.address} onChange={e => setProfileForm({ ...profileForm, address: e.target.value })} />
                        </div>
                    </div>

                    {/* البيانات المهنية */}
                    <div style={{ borderTop: '1px solid var(--ktra-border)', paddingTop: 12, marginTop: 12 }}>
                        <div style={{ fontSize: 'var(--ktra-fs-base, 13px)', fontWeight: 600, color: 'var(--ktra-ink)', marginBottom: 10 }}>البيانات المهنية</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                            <div style={fieldStyle}>
                                <label style={labelStyle}>المؤهل الدراسي</label>
                                <select className="ktra-input" value={profileForm.educationLevel} onChange={e => setProfileForm({ ...profileForm, educationLevel: e.target.value })}>
                                    <option value="">اختر المؤهل...</option>
                                    <option value="High School">ثانوية عامة</option>
                                    <option value="Diploma">دبلوم</option>
                                    <option value="Bachelor">بكالوريوس</option>
                                    <option value="Master">ماجستير</option>
                                    <option value="PhD">دكتوراه</option>
                                </select>
                            </div>
                            <div style={fieldStyle}>
                                <label style={labelStyle}>نبذة عن الخبرات</label>
                                <textarea
                                    className="ktra-input"
                                    rows={3}
                                    value={profileForm.experienceDescription}
                                    onChange={e => setProfileForm({ ...profileForm, experienceDescription: e.target.value })}
                                    style={{ resize: 'vertical' }}
                                />
                            </div>
                            <div style={fieldStyle}>
                                <label style={labelStyle}>
                                    تحديث السيرة الذاتية
                                    {user.resumeData && <span style={{ color: 'var(--ktra-ok, #267346)', marginRight: 6, fontWeight: 400 }}>محفوظ: {user.resumeData.name}</span>}
                                </label>
                                <input type="file" accept=".pdf,.doc,.docx" onChange={handleFileChange} style={{ fontSize: 'var(--ktra-fs-sm)' }} />
                                <span style={{ fontSize: '10px', color: 'var(--ktra-ink-soft)' }}>الحد الأقصى 800 كيلوبايت</span>
                            </div>
                        </div>
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'flex-start', marginTop: 14 }}>
                        <button type="submit" className="ktra-toolbtn" disabled={loadingProfile} style={{ padding: '5px 16px', color: 'var(--ktra-accent, #1857a4)', fontWeight: 700 }}>
                            {loadingProfile ? 'جاري الحفظ...' : 'حفظ التغييرات'}
                        </button>
                    </div>
                </div>
            </form>

            {/* تغيير كلمة المرور */}
            <form onSubmit={handlePasswordChange}>
                <div style={sectionStyle}>
                    <div style={sectionTitleStyle}>تغيير كلمة المرور</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 380 }}>
                        <div style={fieldStyle}>
                            <label style={labelStyle}>كلمة المرور الحالية</label>
                            <input className="ktra-input" type="password" required value={passwordForm.oldPassword} onChange={e => setPasswordForm({ ...passwordForm, oldPassword: e.target.value })} />
                        </div>
                        <div style={fieldStyle}>
                            <label style={labelStyle}>كلمة المرور الجديدة</label>
                            <input className="ktra-input" type="password" required value={passwordForm.newPassword} onChange={e => setPasswordForm({ ...passwordForm, newPassword: e.target.value })} />
                        </div>
                        <div style={fieldStyle}>
                            <label style={labelStyle}>تأكيد كلمة المرور الجديدة</label>
                            <input className="ktra-input" type="password" required value={passwordForm.confirmPassword} onChange={e => setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })} />
                        </div>
                    </div>
                    <div style={{ marginTop: 14 }}>
                        <button type="submit" className="ktra-toolbtn" disabled={loadingPassword} style={{ padding: '5px 16px', fontWeight: 700 }}>
                            {loadingPassword ? 'جاري التحديث...' : 'تحديث كلمة المرور'}
                        </button>
                    </div>
                </div>
            </form>

            {/* task16 D14: اختصارات الوصول السريع في الشريط العلوي */}
            <div style={sectionStyle}>
                <div style={sectionTitleStyle}>اختصارات الوصول السريع (الشريط العلوي)</div>
                <p style={{ fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-ink-soft)', marginBottom: 12 }}>
                    اختر الشاشات التي تظهر كأزرار اختصار أعلى الصفحة للوصول السريع.
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                    {SHORTCUTABLE_VIEWS.map((s) => (
                        <label key={s.view} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-ink)' }}>
                            <input
                                type="checkbox"
                                checked={quickShortcuts.includes(s.view)}
                                onChange={() => toggleShortcut(s.view)}
                            />
                            {s.label}
                        </label>
                    ))}
                </div>
            </div>

            {/* المظهر — حجم الخط ونوعه */}
            <div style={sectionStyle}>
                <div style={sectionTitleStyle}>المظهر — الخط</div>
                <p style={{ fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-ink-soft)', marginBottom: 12 }}>
                    تحكّم بحجم الخط ونوعه في كامل الواجهة. يُطبَّق فوراً ويُحفظ لهذه الشركة (يثبت عند إعادة الدخول وعبر الأجهزة).
                </p>
                <div style={gridStyle}>
                    <div style={fieldStyle}>
                        <label style={labelStyle}>مظهر الواجهة</label>
                        <select
                            className="ktra-input"
                            value={uiSkin}
                            onChange={e => setSkin(e.target.value as UiSkin)}
                        >
                            {/* الجلد الكلاسيكي **باقٍ خياراً كاملاً** (قرار
                                المالك 2026-08-25) — المُلغى مرجعيةُ «الأصيل»
                                لا مظهره. والقيمة القديمة `aseel` ما زالت
                                تُقرأ من تخزين المستخدمين (`styles/skin.ts`). */}
                            <option value="classic">كلاسيكي</option>
                            <option value="modern">حديث</option>
                        </select>
                    </div>
                    <div style={fieldStyle}>
                        <label style={labelStyle}>حجم الخط</label>
                        <select
                            className="ktra-input"
                            value={fontScale}
                            onChange={e => setFontScale(e.target.value as any)}
                        >
                            {FONT_SCALE_OPTIONS.map(o => (
                                <option key={o.id} value={o.id}>{o.label}</option>
                            ))}
                        </select>
                    </div>
                    <div style={fieldStyle}>
                        <label style={labelStyle}>نوع الخط</label>
                        <select
                            className="ktra-input"
                            value={fontFamily}
                            onChange={e => setFontFamily(e.target.value as any)}
                        >
                            {FONT_FAMILY_OPTIONS.map(o => (
                                <option key={o.id} value={o.id}>{o.label}</option>
                            ))}
                        </select>
                    </div>
                </div>
            </div>

            {/* الجلسة والخمول — مهلة إنهاء الجلسة عند عدم النشاط */}
            <div style={sectionStyle}>
                <div style={sectionTitleStyle}>الجلسة والخمول</div>
                <p style={{ fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-ink-soft)', marginBottom: 12 }}>
                    عند عدم وجود أي نشاط (نقر/كتابة/تمرير) طوال هذه المدة تُنهى الجلسة تلقائياً وتُطلب
                    إعادة الدخول. يظهر تنبيه بعدّاد تنازلي قبل الانتهاء لتمديد الجلسة. يُحفظ لهذه الشركة.
                </p>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
                    <div style={{ ...fieldStyle, maxWidth: 220 }}>
                        <label style={labelStyle}>مدة الخمول قبل إنهاء الجلسة (بالدقائق)</label>
                        <input
                            className="ktra-input ktra-num"
                            type="number"
                            min={IDLE_MIN_MINUTES}
                            max={IDLE_MAX_MINUTES}
                            step={5}
                            value={idleInput}
                            onChange={e => setIdleInput(e.target.value)}
                            onBlur={commitIdleTimeout}
                            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); commitIdleTimeout(); } }}
                        />
                        <span style={{ fontSize: '10px', color: 'var(--ktra-ink-soft)' }}>
                            من {IDLE_MIN_MINUTES} دقائق حتى {IDLE_MAX_MINUTES} دقيقة (24 ساعة)
                        </span>
                    </div>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {[30, 60, 120, 180].map((m) => (
                            <button
                                key={m}
                                type="button"
                                className="ktra-toolbtn"
                                onClick={() => setIdleTimeoutMinutes(m)}
                                style={{
                                    padding: '5px 12px', fontWeight: 700,
                                    ...(idleTimeoutMinutes === m ? { color: 'var(--ktra-accent, #1857a4)', borderColor: 'var(--ktra-accent, #1857a4)' } : {}),
                                }}
                            >
                                {m < 60 ? `${m} دقيقة` : `${m / 60} ساعة`}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* أجهزةُ الدخول — ISSUE #168. شاشةُ أمانٍ شخصيّةٌ لصاحب الحساب، وموضعُها
                هنا بجانب «تغيير كلمة المرور» و«الجلسة والخمول» لا في لوحة إدارة. */}
            <div style={sectionStyle}>
                <div style={sectionTitleStyle}>أجهزة الدخول</div>
                <p style={{ fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-ink-soft)', marginBottom: 12 }}>
                    كلُّ جهازٍ دخل بحسابك له مفتاحُه الخاصّ، فإنهاءُ أحدها لا يُخرج البقيّة.
                    «آخر نشاط» يُحدَّث كل خمس دقائق تقريباً.
                </p>

                {devicesGuard ? (
                    // الجهازُ الثانويُّ يرى تفسيراً يسمّي الأساسيَّ لا فراغاً بلا سبب.
                    <div style={{ fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-ink)' }}>
                        <p style={{ marginBottom: 10 }}>{devicesGuard}</p>
                        <button type="button" className="ktra-toolbtn" style={{ padding: '5px 14px', fontWeight: 700 }}
                            onClick={() => setPrimaryPrompt(true)}>
                            اجعل هذا الجهاز أساسيّاً
                        </button>
                    </div>
                ) : (
                    <>
                        {devicesInvitation && (
                            <p style={{ fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-accent, #1857a4)', marginBottom: 10 }}>
                                {devicesInvitation}
                            </p>
                        )}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {devices.map((d) => (
                                <div key={d.id} style={{
                                    border: '1px solid var(--ktra-border)', borderRadius: 6, padding: '10px 12px',
                                    display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
                                }}>
                                    <div style={{ flex: 1, minWidth: 200 }}>
                                        <div style={{ fontSize: 'var(--ktra-fs-sm)', fontWeight: 600, color: 'var(--ktra-ink)' }}>
                                            {d.name}
                                            {d.is_current && (
                                                <span style={{ color: 'var(--ktra-ok, #267346)', marginRight: 6, fontWeight: 700 }}>
                                                    — هذا الجهاز
                                                </span>
                                            )}
                                            {d.is_primary && (
                                                <span style={{ color: 'var(--ktra-accent, #1857a4)', marginRight: 6, fontWeight: 700 }}>
                                                    — الأساسيّ
                                                </span>
                                            )}
                                        </div>
                                        <div style={{ fontSize: '10px', color: 'var(--ktra-ink-soft)' }}>
                                            {d.ip_address || 'بلا عنوان'} · دخل {formatDateTimeValue(d.created_at) || '—'}
                                            {' · '}آخر نشاط {formatDateTimeValue(d.last_active_at) || '—'}
                                        </div>
                                    </div>
                                    {renamingId === d.id ? (
                                        <>
                                            <input
                                                className="ktra-input"
                                                style={{ maxWidth: 160 }}
                                                autoFocus
                                                placeholder="حاسوب المكتب"
                                                value={renameValue}
                                                onChange={e => setRenameValue(e.target.value)}
                                                onKeyDown={e => {
                                                    if (e.key === 'Enter') { e.preventDefault(); void commitRename(d.id); }
                                                    if (e.key === 'Escape') { setRenamingId(null); setRenameValue(''); }
                                                }}
                                            />
                                            <button type="button" className="ktra-toolbtn" style={{ padding: '4px 10px', fontWeight: 700 }}
                                                onClick={() => void commitRename(d.id)}>
                                                حفظ
                                            </button>
                                        </>
                                    ) : (
                                        <button type="button" className="ktra-toolbtn" style={{ padding: '4px 10px' }}
                                            onClick={() => { setRenamingId(d.id); setRenameValue(d.label || ''); }}>
                                            تسمية
                                        </button>
                                    )}
                                    {/* الأساسيُّ لا يُخرَج من هنا — الخروجُ العاديُّ بابُه. */}
                                    {!d.is_primary && (
                                        <button type="button" className="ktra-toolbtn" style={{ padding: '4px 10px', color: 'var(--ktra-danger, #b42318)' }}
                                            onClick={() => void handleEvictDevice(d)}>
                                            إنهاء
                                        </button>
                                    )}
                                </div>
                            ))}
                            {devices.length === 0 && (
                                <span style={{ fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-ink-soft)' }}>
                                    لا أجهزة لعرضها.
                                </span>
                            )}
                        </div>
                        <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                            <button type="button" className="ktra-toolbtn" style={{ padding: '5px 14px', fontWeight: 700 }}
                                onClick={() => setPrimaryPrompt(true)}>
                                اجعل هذا الجهاز أساسيّاً
                            </button>
                            <button type="button" className="ktra-toolbtn"
                                style={{ padding: '5px 14px', fontWeight: 700, color: 'var(--ktra-danger, #b42318)' }}
                                onClick={() => void handleEvictOthers()}>
                                أخرِج كلَّ الأجهزة الأخرى
                            </button>
                        </div>
                    </>
                )}

                {primaryPrompt && (
                    <div style={{ borderTop: '1px solid var(--ktra-border)', marginTop: 12, paddingTop: 12, maxWidth: 320 }}>
                        <div style={fieldStyle}>
                            {/* حقلٌ داخل الصفحة لا `window.prompt` — كلمةُ المرور لا تمرّ بحوار متصفّح. */}
                            <label style={labelStyle}>كلمة المرور لتأكيد التنصيب</label>
                            <input className="ktra-input" type="password" value={primaryPassword}
                                onChange={e => setPrimaryPassword(e.target.value)} />
                        </div>
                        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                            <button type="button" className="ktra-toolbtn" style={{ padding: '5px 14px', fontWeight: 700 }}
                                onClick={() => void handleSetPrimary()}>
                                تأكيد
                            </button>
                            <button type="button" className="ktra-toolbtn" style={{ padding: '5px 14px' }}
                                onClick={() => { setPrimaryPrompt(false); setPrimaryPassword(''); }}>
                                إلغاء
                            </button>
                        </div>
                    </div>
                )}
            </div>

            {/* خصوصية عرض الأسعار والأرباح (زر العين) */}
            <div style={sectionStyle}>
                <div style={sectionTitleStyle}>خصوصية الأسعار والأرباح (زر العين)</div>
                <p style={{ fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-ink-soft)', marginBottom: 12 }}>
                    زر العين في الشريط العلوي يُظهر/يُخفي أسعار القوائم والربح الإجمالي في الفاتورة —
                    للخصوصية حين يجلس الزبون أمام الشاشة.
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-ink)' }}>
                        <input
                            type="checkbox"
                            checked={showToggle}
                            onChange={(e) => setShowToggle(e.target.checked)}
                        />
                        إظهار زر العين في الشريط العلوي (لإظهار/إخفاء الأسعار والأرباح)
                    </label>
                    {!showToggle && (
                        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-ink)', paddingInlineStart: 24 }}>
                            <input
                                type="checkbox"
                                checked={defaultVisible}
                                onChange={(e) => setDefaultVisible(e.target.checked)}
                            />
                            إظهار الأرباح والتكاليف في الفاتورة افتراضياً (بما أن زر العين مخفي)
                        </label>
                    )}
                </div>
            </div>

            {/* P5-T1-b: إدارة التخزين المحلي.
                T-SIMPL2: زرٌّ تقنيّ للتشخيص — يُطوى في الوضع السهل. */}
            {showAdv('settings.local-cache') && (
            <div className="ktra-form-section" style={{ marginTop: 20 }}>
                <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>إدارة التخزين المحلي</h3>
                <p style={{ fontSize: 13, color: '#64748b', marginBottom: 12 }}>
                    البيانات المخزنة محلياً (cache) تتيح تصفح التطبيق بدون اتصال.
                </p>
                <button
                    type="button"
                    className="ktra-toolbtn"
                    /* عطلان كانا هنا (وُجدا أثناء عملٍ آخر، خارج نطاقه):
                       (1) رسالةُ **نجاحٍ** بنبرة `error` — حمراء تقول «تم»، فيظنّ
                           المستخدم أن المسح أخفق وقد نجح.
                       (2) `cleanOldCache` تفتح IndexedDB وقد ترمي (وضع خاص،
                           حصّةٌ ممتلئة، قاعدة مقفولة) بلا `catch` — فالوعد يسقط
                           في الفراغ والزرّ يبدو بلا أثر. لا فشل صامت. */
                    onClick={async () => {
                        try {
                            const { cleanOldCache } = await import('../services/offline/cacheCleaner');
                            const n = await cleanOldCache(7);
                            toast(
                                n > 0 ? `تم حذف ${n} سجل قديم` : 'لا سجلات أقدم من 7 أيام — لا شيء ليُحذف',
                                n > 0 ? 'success' : 'info',
                            );
                        } catch (e) {
                            toast(humanizeThrown(e, 'تعذّر مسح الـcache القديم'), 'error');
                        }
                    }}
                    style={{ padding: '5px 16px', fontWeight: 700 }}
                >
                    امسح cache قديم (أقدم من 7 أيام)
                </button>
            </div>
            )}
        </div>
    );
};
