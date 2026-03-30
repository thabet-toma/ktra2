# توثيق شامل لمشروع منصة البحث الذكي - Smart Product Search Platform

هذا الملف يحتوي على الأكواد البرمجية الأساسية للمشروع مع شرح مفصل لكل جزء باللغة العربية. تم التركيز على "الدماغ" المحرك للتطبيق (Core Logic) لضمان فهم كيفية عمل النظام بالكامل.

---

## 1. الملف الرئيسي والمتحكم: `App.tsx`
هذا الملف هو نقطة التجمع لكل مكونات التطبيق. يدير الحالة العامة، التنقل، والاشتراكات في قاعدة البيانات.

### شرح المكونات الرئيسية في `App.tsx`:
- **State Management**: يستخدم `useState` لمتابعة المهام (`tasks`) والمستخدمين (`users`).
- **Sidebar & Header**: المكونات الثابتة التي تظهر في كل الصفحات.
- **Main Router**: دالة `renderMainContent` التي تقرر أي صفحة تظهر للمستخدم بناءً على `appView`.

```tsx
// [تم اختصار الاستيرادات للتركيز على الشرح]
const App: React.FC = () => {
    // جلب بيانات المستخدم المسجل والتحقق من صلاحياته
    const { currentUser, loading: authLoading, logout, updateUser } = useAuth();
    
    // الاشتراك في تحديثات المهام والوقت من Firebase
    useEffect(() => {
        if (!currentUser) return;
        const unsubscribe = subscribeToTasks((fetchedTasks) => setTasks(fetchedTasks));
        return unsubscribe;
    }, [currentUser]);

    // معالجة بدء مهمة جديدة (Timer)
    const startUserTask = async (taskId: string) => {
        if (!currentUser) return;
        // ... (تسجيل وقت البدء في Firestore)
    };

    // التنقل بين الشاشات
    const renderMainContent = () => {
        switch (appView) {
            case "dashboard": return <Dashboard ... />;
            case "tasks": return <TaskList ... />;
            case "task-management": return <TaskManagement ... />;
            // ... (باقي الشاشات: الإدارة، التقارير، الحسابات، الموردين)
        }
    };

    return (
        <div dir="rtl" className="...">
            <Sidebar ... />
            <div className="flex-1 flex flex-col">
                <Header ... />
                <main>{renderMainContent()}</main>
            </div>
        </div>
    );
};
```

---

## 2. محرك التعامل مع البيانات: `services/firestoreService.ts`
هذا الملف هو الأكبر والأهم، حيث يحتوي على جميع الدوال التي تتعامل مع **Firebase Firestore**.

### الأقسام المشروحة:
- **نظام النقاط النشط**: دوال `initializeActivityStatus` و `recordCheckIn` المسؤولة عن متابعة نشاط الموظف وتحفيزه بالنقاط.
- **إدارة الموردين والسلع**: دوال `suppliersService` و `itemsService` للتحكم في قاعدة بيانات الموردين.
- **إدارة الحسابات (Finance)**: نظام `cashBoxesService` لإدارة الصناديق المالية والحركات (Deposits/Withdrawals).

```typescript
// مثال: دالة الاشتراك في المهام
export const subscribeToTasks = (callback: (tasks: Task[]) => void) => {
    const q = query(collection(db, "tasks"), orderBy("updatedAt", "desc"));
    return onSnapshot(q, (snapshot) => {
        const tasks = snapshot.docs.map(doc => doc.data() as Task);
        callback(tasks);
    });
};

// مثال: تحديث حالة المهمة
export const updateUserTaskStatus = async (taskId: string, userId: string, status: any) => {
    const taskRef = doc(db, "tasks", taskId);
    await updateDoc(taskRef, {
        [`userStatuses.${userId}`]: { ...status, updatedAt: new Date().toISOString() }
    });
};
```

---

## 3. محرك الذكاء الاصطناعي: `services/geminiService.ts`
يستخدم هذا الملف مكتبة `@google/genai` للتواصل مع نموذج **Gemini 2.5 Flash**.

### الوظيفة:
عندما يقوم الموظف برفع صورة منتج ووصفه، تقوم الدالة `findProducts` بإرسال الصورة والوصف للذكاء الاصطناعي الذي يقوم بدوره بتحليل المنتج وتقديم توصيات (اسم المورد، السعر المتوقع، رابط البحث في علي بابا).

```typescript
export const findProducts = async (query: SearchQuery): Promise<Product[]> => {
    const promptText = `حلل صورة هذا المنتج ووصفه: "${query.description}". قدم لي 6-10 ترشيحات واقعية من السوق الصيني (علي بابا، 1688).`;
    const response = await ai.models.generateContent({
        model: "gemini-2.5-flash",
        contents: { parts: [imagePart, { text: promptText }] },
        // ... (تنسيق المخرجات كـ JSON)
    });
    return JSON.parse(response.text).products;
};
```

---

## 4. نظام الهوية والجلسات: `contexts/AuthContext.tsx`
يوفر هذا الملف "Context" يغلف التطبيق بالكامل لمعرفة من هو المستخدم المسجل وما هي صلاحياته (مدير، موظف، مشتريات).

---

## 5. تعريفات البيانات: `types/index.ts`
يحتوي على الـ `Interfaces` التي تضمن أن البيانات متسقة في كل مكان (Task, User, Product, Supplier, Invoice, Deal, Shipment).

---

### ملاحظة ختامية:
تم اختصار التقرير ليركز على الأكواد التي كتبت خصيصاً للمنطق البرمجي (Core Code). المجلد `components` يحتوي على ملفات الواجهات (UI) وهي تتبع نفس النمط البرمجي التفاعلي باستخدام `Tailwind CSS`. إذا كنت بحاجة لكود مكون معين (مثل شاشة التقارير أو فاتورة الشراء) يرجى طلبي بالاسم.
