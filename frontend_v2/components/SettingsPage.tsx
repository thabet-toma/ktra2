/**
 * N7-T7 — SettingsPage — Aseel form sections
 */
import React, { useState, useEffect } from 'react';
import { User } from '../types';
import { updateUserInDb } from '../services/firestoreService';
import { changeUserPassword } from '../services/authService';

interface SettingsPageProps {
    user: User;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({ user }) => {
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

    useEffect(() => {
        setProfileForm({
            name: user.name, phone: user.phone || '', address: user.address || '',
            educationLevel: user.educationLevel || '', experienceDescription: user.experienceDescription || '',
        });
    }, [user]);

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

    const sectionStyle: React.CSSProperties = { border: '1px solid var(--aseel-border)', borderRadius: 6, padding: '14px 18px', marginBottom: 14 };
    const sectionTitleStyle: React.CSSProperties = { fontSize: 'var(--aseel-fs-title, 14px)', fontWeight: 700, color: 'var(--aseel-ink)', marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid var(--aseel-border)' };
    const fieldStyle: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4 };
    const labelStyle: React.CSSProperties = { fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)', fontWeight: 500 };
    const gridStyle: React.CSSProperties = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 };

    return (
        <div dir="rtl" data-skin="aseel" style={{ padding: '8px 12px', maxWidth: 780 }}>
            {/* العنوان */}
            <div style={{ paddingBottom: 8, borderBottom: '1px solid var(--aseel-border)', marginBottom: 14 }}>
                <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>الإعدادات</strong>
            </div>

            {/* رسالة الحالة */}
            {message && (
                <div style={{ padding: '8px 12px', borderRadius: 6, marginBottom: 12, fontSize: 'var(--aseel-fs-sm)', background: message.type === 'success' ? 'rgba(38,115,70,0.08)' : 'rgba(204,0,0,0.08)', color: message.type === 'success' ? 'var(--aseel-ok, #267346)' : 'var(--aseel-danger, #c00)', border: `1px solid ${message.type === 'success' ? 'var(--aseel-ok, #267346)' : 'var(--aseel-danger, #c00)'}` }}>
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
                            <input className="aseel-input" required value={profileForm.name} onChange={e => setProfileForm({ ...profileForm, name: e.target.value })} />
                        </div>
                        <div style={fieldStyle}>
                            <label style={labelStyle}>البريد الإلكتروني (للقراءة فقط)</label>
                            <input className="aseel-input" type="email" value={user.email} disabled style={{ opacity: 0.6, cursor: 'not-allowed' }} />
                        </div>
                        <div style={fieldStyle}>
                            <label style={labelStyle}>رقم الهاتف</label>
                            <input className="aseel-input" type="tel" value={profileForm.phone} onChange={e => setProfileForm({ ...profileForm, phone: e.target.value })} />
                        </div>
                        <div style={fieldStyle}>
                            <label style={labelStyle}>العنوان</label>
                            <input className="aseel-input" value={profileForm.address} onChange={e => setProfileForm({ ...profileForm, address: e.target.value })} />
                        </div>
                    </div>

                    {/* البيانات المهنية */}
                    <div style={{ borderTop: '1px solid var(--aseel-border)', paddingTop: 12, marginTop: 12 }}>
                        <div style={{ fontSize: 'var(--aseel-fs-base, 13px)', fontWeight: 600, color: 'var(--aseel-ink)', marginBottom: 10 }}>البيانات المهنية</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                            <div style={fieldStyle}>
                                <label style={labelStyle}>المؤهل الدراسي</label>
                                <select className="aseel-input" value={profileForm.educationLevel} onChange={e => setProfileForm({ ...profileForm, educationLevel: e.target.value })}>
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
                                    className="aseel-input"
                                    rows={3}
                                    value={profileForm.experienceDescription}
                                    onChange={e => setProfileForm({ ...profileForm, experienceDescription: e.target.value })}
                                    style={{ resize: 'vertical' }}
                                />
                            </div>
                            <div style={fieldStyle}>
                                <label style={labelStyle}>
                                    تحديث السيرة الذاتية
                                    {user.resumeData && <span style={{ color: 'var(--aseel-ok, #267346)', marginRight: 6, fontWeight: 400 }}>محفوظ: {user.resumeData.name}</span>}
                                </label>
                                <input type="file" accept=".pdf,.doc,.docx" onChange={handleFileChange} style={{ fontSize: 'var(--aseel-fs-sm)' }} />
                                <span style={{ fontSize: '10px', color: 'var(--aseel-ink-soft)' }}>الحد الأقصى 800 كيلوبايت</span>
                            </div>
                        </div>
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'flex-start', marginTop: 14 }}>
                        <button type="submit" className="aseel-toolbtn" disabled={loadingProfile} style={{ padding: '5px 16px', color: 'var(--aseel-accent, #1857a4)', fontWeight: 700 }}>
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
                            <input className="aseel-input" type="password" required value={passwordForm.oldPassword} onChange={e => setPasswordForm({ ...passwordForm, oldPassword: e.target.value })} />
                        </div>
                        <div style={fieldStyle}>
                            <label style={labelStyle}>كلمة المرور الجديدة</label>
                            <input className="aseel-input" type="password" required value={passwordForm.newPassword} onChange={e => setPasswordForm({ ...passwordForm, newPassword: e.target.value })} />
                        </div>
                        <div style={fieldStyle}>
                            <label style={labelStyle}>تأكيد كلمة المرور الجديدة</label>
                            <input className="aseel-input" type="password" required value={passwordForm.confirmPassword} onChange={e => setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })} />
                        </div>
                    </div>
                    <div style={{ marginTop: 14 }}>
                        <button type="submit" className="aseel-toolbtn" disabled={loadingPassword} style={{ padding: '5px 16px', fontWeight: 700 }}>
                            {loadingPassword ? 'جاري التحديث...' : 'تحديث كلمة المرور'}
                        </button>
                    </div>
                </div>
            </form>
        </div>
    );
};
