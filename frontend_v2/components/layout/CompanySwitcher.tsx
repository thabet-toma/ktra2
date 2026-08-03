import React, { useState, useRef, useEffect } from "react";
import { useCompany, Tenant } from "../../contexts/CompanyContext";
import { useTenantSettings } from "../../hooks/useTenantSettings";
import { Building, Plus, ChevronDown, Check, Loader2, Settings2, Star } from "lucide-react";
import { CompanyManagementModal, ROLE_LABELS } from "./CompanyManagementModal";

const companyLabel = (tenant: Tenant) =>
  `${tenant.CompanyName}${tenant.is_example ? " (مثال)" : ""}`;

export const CompanySwitcher: React.FC = () => {
  const { companies, currentCompany, switchCompany, createCompany, setDefaultCompany, loading, refreshCompanies } = useCompany();
  const { identity } = useTenantSettings();
  const activeMembership = companies.find(
    (membership) => membership.tenant.TenantID === currentCompany?.TenantID
  );
  const canManageCurrentCompany = activeMembership?.role === "manager";
  const [isOpen, setIsOpen] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [showManageModal, setShowManageModal] = useState(false);
  const [newCompanyName, setNewCompanyName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pinning, setPinning] = useState<number | null>(null);

  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = async (tenant: Tenant) => {
    if (currentCompany?.TenantID === tenant.TenantID) {
      setIsOpen(false);
      return;
    }
    await switchCompany(tenant.TenantID);
    setIsOpen(false);
  };

  /** T-IMPOFFER: النجمة تثبّت الشركة التي تُفتح أول ما يدخل المستخدم. */
  const handlePinDefault = async (tenantId: number) => {
    setPinning(tenantId);
    setError(null);
    try {
      await setDefaultCompany(tenantId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "فشل تعيين الشركة الافتراضية");
    } finally {
      setPinning(null);
    }
  };

  const handleCreateCompany = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCompanyName.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await createCompany(newCompanyName);
      setShowModal(false);
      setNewCompanyName("");
      // Switch to newly created company automatically
      await switchCompany(created.TenantID);
    } catch (err) {
      setError(err instanceof Error ? err.message : "فشل إنشاء الشركة");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading && !currentCompany) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 text-sm text-[var(--color-text-secondary)]">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>جاري تحميل الشركات...</span>
      </div>
    );
  }

  return (
    <div className="relative inline-block text-right" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 text-sm font-semibold rounded-lg bg-[var(--aseel-panel)] border border-[var(--aseel-border-soft)] hover:bg-[var(--aseel-panel-hover)] transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[var(--aseel-accent)]"
        style={{ color: "var(--aseel-ink)" }}
      >
        {identity?.logo_url ? (
          <img src={identity.logo_url} alt="Logo" className="w-5 h-5 rounded object-cover bg-[var(--color-surface)]" />
        ) : (
          <Building className="w-4 h-4 opacity-70" />
        )}
        <span>{currentCompany ? companyLabel(currentCompany) : "اختر الشركة"}</span>
        <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-1.5 w-64 rounded-xl shadow-xl bg-[var(--aseel-bg)] border border-[var(--aseel-border)] z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150">
          <div className="px-4 py-2.5 bg-[var(--aseel-panel)] border-b border-[var(--aseel-border-soft)]">
            <span className="text-[11px] font-bold tracking-wider uppercase opacity-60">الشركات والمجموعات</span>
          </div>

          <div className="max-h-60 overflow-y-auto py-1">
            {companies.map((membership) => {
              const isActive = currentCompany?.TenantID === membership.tenant.TenantID;
              return (
                <div
                  key={membership.id}
                  className={`w-full flex items-center gap-1 pl-1.5 pr-4 transition-colors duration-150 hover:bg-[var(--aseel-panel-hover)] ${isActive ? "bg-[var(--aseel-panel-hover)] font-bold" : ""}`}
                >
                  <button
                    type="button"
                    onClick={() => handleSelect(membership.tenant)}
                    className="flex flex-1 items-center justify-between py-2.5 text-sm text-right"
                  >
                    <div className="flex flex-col">
                      <span style={{ color: isActive ? "var(--aseel-accent)" : "var(--aseel-ink)" }}>
                        {companyLabel(membership.tenant)}
                      </span>
                      <span className="text-[11px] opacity-60">
                        الدور: {ROLE_LABELS[membership.role] || membership.role}
                        {membership.is_default && " · افتراضية"}
                      </span>
                    </div>
                    {isActive && <Check className="w-4 h-4 text-[var(--aseel-accent)]" />}
                  </button>
                  {/* T-IMPOFFER: تثبيت الشركة التي تُفتح عند الدخول. */}
                  <button
                    type="button"
                    disabled={membership.is_default || pinning != null}
                    onClick={() => void handlePinDefault(membership.tenant.TenantID)}
                    className="p-1.5 rounded-lg hover:bg-[var(--aseel-panel)] disabled:cursor-default transition-colors"
                    title={membership.is_default ? "الشركة الافتراضية عند الدخول" : "اجعلها الشركة الافتراضية عند الدخول"}
                    aria-label="الشركة الافتراضية"
                  >
                    {pinning === membership.tenant.TenantID ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Star
                        className="w-3.5 h-3.5"
                        style={{
                          color: membership.is_default ? "var(--aseel-accent)" : "var(--aseel-ink-soft)",
                          fill: membership.is_default ? "var(--aseel-accent)" : "none",
                        }}
                      />
                    )}
                  </button>
                </div>
              );
            })}
            {error && !showModal && (
              <p className="px-4 py-2 text-[11px] font-semibold text-[var(--color-danger)]">
                {error}
              </p>
            )}
          </div>

          <div className="border-t border-[var(--aseel-border-soft)] p-1.5 bg-[var(--aseel-panel)] space-y-1.5">
            {currentCompany && canManageCurrentCompany && (
              <button
                type="button"
                onClick={() => {
                  setShowManageModal(true);
                  setIsOpen(false);
                }}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 text-xs font-bold rounded-lg border border-[var(--aseel-border)] hover:bg-[var(--aseel-panel-hover)] transition-colors duration-150 focus:outline-none"
                style={{ color: "var(--aseel-ink)" }}
              >
                <Settings2 className="w-3.5 h-3.5" />
                <span>إدارة الشركة (الاسم والأعضاء)</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                setShowModal(true);
                setIsOpen(false);
              }}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 text-xs font-bold text-white rounded-lg bg-[var(--aseel-accent)] hover:bg-[var(--aseel-accent-dark,var(--aseel-accent))] transition-colors duration-150 focus:outline-none"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>إنشاء شركة جديدة</span>
            </button>
          </div>
        </div>
      )}

      {/* Company Management Modal — task12 M4 */}
      {showManageModal && currentCompany && canManageCurrentCompany && (
        <CompanyManagementModal
          isOpen={showManageModal}
          onClose={() => setShowManageModal(false)}
          memberships={companies}
          initialTenantId={currentCompany.TenantID}
          onChanged={refreshCompanies}
        />
      )}

      {/* Create Company Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100] p-4 animate-in fade-in duration-200">
          <div
            className="w-full max-w-md rounded-2xl bg-[var(--aseel-bg)] border border-[var(--aseel-border)] shadow-2xl p-6 overflow-hidden transform transition-all animate-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-bold" style={{ color: "var(--aseel-ink)" }}>إنشاء شركة / مجموعة جديدة</h3>
              <button
                type="button"
                onClick={() => {
                  setShowModal(false);
                  setError(null);
                  setNewCompanyName("");
                }}
                className="p-1 rounded-lg hover:bg-[var(--aseel-panel-hover)] transition-colors opacity-70 hover:opacity-100"
              >
                <Plus className="w-5 h-5 rotate-45" />
              </button>
            </div>

            <form onSubmit={handleCreateCompany} className="space-y-5">
              {error && (
                <div className="p-3 text-xs bg-[color-mix(in_srgb,var(--color-danger)_10%,transparent)] text-[var(--color-danger)] rounded-lg border border-[color-mix(in_srgb,var(--color-danger)_35%,transparent)] font-semibold">
                  {error}
                </div>
              )}

              <div className="space-y-1.5">
                <label className="text-xs font-bold opacity-80" htmlFor="company-name">اسم الشركة</label>
                <input
                  id="company-name"
                  type="text"
                  required
                  placeholder="مثال: شركة القدس للتجارة"
                  value={newCompanyName}
                  onChange={(e) => setNewCompanyName(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--aseel-border)] bg-[var(--aseel-panel)] focus:outline-none focus:ring-2 focus:ring-[var(--aseel-accent)] focus:border-transparent transition-all duration-200"
                  disabled={submitting}
                />
              </div>

              <div className="flex gap-3 justify-end pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setShowModal(false);
                    setError(null);
                    setNewCompanyName("");
                  }}
                  className="px-4 py-2 text-sm font-semibold rounded-lg hover:bg-[var(--aseel-panel-hover)] transition-colors duration-150"
                  disabled={submitting}
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  className="flex items-center gap-2 px-5 py-2 text-sm font-bold text-white rounded-lg bg-[var(--aseel-accent)] hover:bg-[var(--aseel-accent-dark,var(--aseel-accent))] transition-colors duration-150"
                  disabled={submitting}
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>جاري الإنشاء...</span>
                    </>
                  ) : (
                    <span>إنشاء وتفعيل</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
