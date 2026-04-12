import {
    collection,
    doc,
    setDoc,
    deleteDoc,
    updateDoc,
    onSnapshot,
    query,
    orderBy,
    where,
    getDocs,
    db
} from "./sqlApiClient";
import { SubCategory } from "../types";

export const subCategoriesService = {
    // 1. اشتراك في الفئات الفرعية (Real-time Listener)
    subscribeToSubCategories: (callback: (subCategories: SubCategory[]) => void) => {
        const q = query(collection(db, "subCategories"), orderBy("createdAt", "desc"));
        return onSnapshot(q, (snapshot: any) => {
            const data = snapshot.docs.map((d: any) => ({
                id: d.id,
                ...d.data(),
            }) as SubCategory);
            callback(data);
        });
    },

    // 2. إضافة فئة فرعية جديدة
    addSubCategoryToDb: async (subCategory: SubCategory) => {
        try {
            // استخدام ID المرسل أو إنشاء واحد جديد إذا لم يوجد
            const id = subCategory.id || crypto.randomUUID();
            const subCategoryRef = doc(db, "subCategories", id);

            const newSubCategory = {
                ...subCategory,
                id,
                createdAt: subCategory.createdAt || new Date().toISOString()
            };

            await setDoc(subCategoryRef, newSubCategory);
            console.log("Sub-category added successfully");
        } catch (error) {
            console.error("Error adding sub-category:", error);
            throw error;
        }
    },

    // 3. تحديث فئة فرعية
    updateSubCategoryInDb: async (subCategory: SubCategory) => {
        try {
            if (!subCategory.id) throw new Error("SubCategory ID is required for update");

            const subCategoryRef = doc(db, "subCategories", subCategory.id);
            await updateDoc(subCategoryRef, subCategory as any);
            console.log("Sub-category updated successfully");
        } catch (error) {
            console.error("Error updating sub-category:", error);
            throw error;
        }
    },

    // 4. حذف فئة فرعية
    deleteSubCategoryFromDb: async (id: string) => {
        try {
            const subCategoryRef = doc(db, "subCategories", id);
            await deleteDoc(subCategoryRef);
            console.log("Sub-category deleted successfully");
        } catch (error) {
            console.error("Error deleting sub-category:", error);
            throw error;
        }
    },

    // 5. (اختياري) جلب الفئات الفرعية التابعة لفئة رئيسية معينة (مرة واحدة بدون اشتراك)
    getSubCategoriesByParentId: async (categoryId: string): Promise<SubCategory[]> => {
        try {
            const q = query(
                collection(db, "subCategories"),
                where("categoryId", "==", categoryId)
            );
            const snapshot = await getDocs(q);
            return snapshot.docs.map(
                (d) => ({ id: d.id, ...d.data() }) as SubCategory
            );
        } catch (error) {
            console.error("Error fetching sub-categories by parent:", error);
            return [];
        }
    }
};