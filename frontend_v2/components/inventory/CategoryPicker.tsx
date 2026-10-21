/**
 * C2 — غلافٌ رقيقٌ فوق `CategoryTreeSelect` (وضع `single`): كلُّ مستدعٍ
 * (كرت المنتج، التحرير السريع، الإنشاء السريع من المستندات) يكسب منتقي الشجرة
 * — بحثاً بالمسار الكامل، تصفّحاً، وإنشاءً بموضعٍ صريح — بلا لمس مواضعه.
 *
 * العقد الخارجي لم يتغيّر عمداً: `value`/`onChange(id, name?)`/`className`/
 * `disabled`. والاسم الثاني هو **اسم التصنيف نفسه** لا المسار (هذا ما تقرؤه
 * `ItemForm` في `category_name`)؛ يُقرأ من القائمة المحمَّلة هنا، وإن كان
 * التصنيف قد أُنشئ داخل المنتقي فلن يكون فيها بعد ⇒ تُعاد القائمة ويُؤخذ آخر
 * مقطعٍ من المسار، وهو اسمه.
 *
 * «إدارة التصنيفات» (شجرة الفاتورة) باقية كما هي، ومخفيةٌ عمّن لا يملك
 * `inventory.item.manage` — وكذلك «إنشاء تصنيف» داخل المنتقي نفسه.
 *
 * وقبل استقرار أوّل جلبٍ يعرض شكلاً معطَّلاً «جارٍ التحميل…» مكان المنتقي: تمريرُ
 * قائمةٍ فارغةٍ قبلها كان يُظهر «—» لمنتجٍ له تصنيف. وإن فشل الجلب عُرِض مكانه
 * «تعذّر تحميل التصنيفات» وزرُّ «إعادة المحاولة» (يعود «جارٍ التحميل…» ثم
 * المنتقي عند نجاحها) — لا منتقٍ بقائمةٍ فارغةٍ يُظهر «—» كذلك.
 */
import React, { useCallback, useEffect, useState } from "react";
import { inventoryApi } from "../../services/inventoryApi";
import { X, FolderTree } from "lucide-react";
import { InvoiceCategoryTree } from "../procurement/invoices/InvoiceCategoryTree";
import { PATH_SEPARATOR } from "../../utils/categoryTree";
import { usePermissions } from "../../contexts/PermissionsContext";
import { CategoryTreeSelect } from "./CategoryTreeSelect";

type Category = {
  id: number;
  name: string;
  parent: number | null;
  // backend also returns other fields if any
};

type Props = {
  value: number | null;
  onChange: (id: number | null, name?: string) => void;
  className?: string;
  disabled?: boolean;
};

export const CategoryPicker: React.FC<Props> = ({ value, onChange, className, disabled }) => {
  const { can } = usePermissions();
  const canManageCatalog = can("inventory.item.manage");
  const [categories, setCategories] = useState<Category[]>([]);
  const [showManage, setShowManage] = useState(false);
  // C2: حتى تستقرّ القائمة الأولى يُعرض شكلٌ معطَّل بدل المنتقي — تمريرُ
  // `categories=[]` قبلها كان يُظهر «—» لمنتجٍ له تصنيف.
  const [loaded, setLoaded] = useState(false);
  // وفشلُ الجلب لا يُعرض منتقياً بقائمةٍ فارغة («—» لمنتجٍ له تصنيف)، بل
  // رسالةٌ وزرُّ إعادة محاولة.
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await inventoryApi.getCategories();
      setCategories(Array.isArray(data) ? (data as Category[]) : []);
      setLoadError(false);
    } catch (e) {
      console.error("Failed to load categories", e);
      setLoadError(true);
    } finally {
      setLoaded(true);
    }
  }, []);

  /** إعادة المحاولة تعود إلى «جارٍ التحميل…» ثم تعرض المنتقي أو الرسالة. */
  const retryLoad = () => {
    setLoaded(false);
    setLoadError(false);
    void load();
  };

  useEffect(() => {
    void load();
  }, [load]);

  const handleChange = (id: number | null, pathLabel: string) => {
    if (id == null) {
      onChange(null, undefined);
      return;
    }
    const known = categories.find((category) => category.id === id);
    if (known) {
      onChange(id, known.name);
      return;
    }
    // أُنشئ داخل المنتقي للتوّ: القائمة هنا لم تحتوِه بعد — تُحدَّث، والاسم من المسار.
    void load();
    onChange(id, pathLabel.split(PATH_SEPARATOR).pop());
  };

  return (
    <div>
      <div className="flex w-full items-center gap-1">
        {loaded ? (
          loadError ? (
            <>
              <div className={`ktra-input min-w-0 flex-1 text-[var(--ktra-danger)] ${className ?? ""}`}>
                تعذّر تحميل التصنيفات
              </div>
              <button
                type="button"
                className="ktra-toolbtn shrink-0"
                onClick={retryLoad}
                disabled={disabled}
              >
                إعادة المحاولة
              </button>
            </>
          ) : (
            <CategoryTreeSelect
              mode="single"
              value={value}
              onChange={handleChange}
              categories={categories}
              className={`min-w-0 flex-1 ${className ?? ""}`}
              disabled={disabled}
              allowCreate
            />
          )
        ) : (
          <div className={`ktra-input min-w-0 flex-1 opacity-60 ${className ?? ""}`}>
            جارٍ التحميل…
          </div>
        )}
        {canManageCatalog && (
          <button
            type="button"
            className="ktra-toolbtn shrink-0"
            onClick={() => setShowManage(true)}
            disabled={disabled}
            title="إدارة التصنيفات (شجرة)"
          >
            <FolderTree className="h-4 w-4" />
          </button>
        )}
      </div>

      {showManage && (
        <CategoryManageModal
          onClose={() => {
            setShowManage(false);
            void load();
          }}
        />
      )}
    </div>
  );
};

const CategoryManageModal: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" dir="rtl">
      <div className="bg-[var(--color-surface)] rounded shadow-xl w-full max-w-md flex flex-col max-h-[80vh] h-[600px]">
        <div className="flex items-center justify-between p-3 border-b bg-[var(--color-surface-2)]">
          <h3 className="font-bold text-[var(--ktra-ink)]">إدارة التصنيفات (شجرة)</h3>
          <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-muted)]"><X className="h-5 w-5" /></button>
        </div>
        <div className="p-0 overflow-hidden flex-1 flex flex-col">
          <InvoiceCategoryTree items={[]} onPickItem={()=>{}} disabled={false} manageMode />
        </div>
      </div>
    </div>
  );
};
