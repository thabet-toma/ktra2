# LITERAL COMPLETE CODEBASE - VERSION 5.0
## PROJECT: Smart Product Search Platform (K.T.R.A)
## DATE: 2026-03-25

> [!IMPORTANT]
> This file contains the LITERAL source code of the project's core services, types, and primary UI components. 
> Every line is numbered for easy reference.

---

### [FILE] [firebaseConfig.ts](file:///c:/Users/asus/Desktop/ثابت/منصة/smart-product-search-platform/firebaseConfig.ts)
1: import { initializeApp } from "firebase/app";
2: import { getFirestore } from "firebase/firestore";
3: import { getAuth } from "firebase/auth";
4: 
5: const env = (import.meta as any).env;
6: 
7: // Use environment variables defined in .env.local
8: const firebaseConfig = {
9:   apiKey: env.VITE_FIREBASE_API_KEY,
10:   authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
11:   projectId: env.VITE_FIREBASE_PROJECT_ID,
12:   storageBucket: env.VITE_FIREBASE_STORAGE_BUCKET,
13:   messagingSenderId: env.VITE_FIREBASE_MESSAGING_SENDER_ID,
14:   appId: env.VITE_FIREBASE_APP_ID
15: };
16: // Initialize Firebase
17: const app = initializeApp(firebaseConfig);
18: 
19: // Initialize Cloud Firestore and get a reference to the service
20: export const db = getFirestore(app);
21: 
22: // Initialize Firebase Authentication
23: export const auth = getAuth(app);
24: 
25: // Initialize Firebase Storage
26: import { getStorage } from "firebase/storage";
27: export const storage = getStorage(app);

---

### [FILE] [index.tsx](file:///c:/Users/asus/Desktop/ثابت/منصة/smart-product-search-platform/index.tsx)
1: // index.tsx - تحديث المسارات
2: import React from 'react';
3: import ReactDOM from 'react-dom/client';
4: import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
5: import App from './App';
6: import PublicGallery from './components/PublicGallery';
7: import AboutUs from './components/AboutUs';
8: import Contact from './components/pages/Contact';
9: import DepartmentModal from './components/pages/DepartmentModal';
10: import { PublicLayout } from './components/layout/PublicLayout';
11: import { StorePage } from './components/store/StorePage';
12: import { ProductDetailPage } from './components/store/ProductDetailPage'; // استيراد صفحة التفاصيل
13: 
14: const rootElement = document.getElementById('root');
15: if (!rootElement) {
16:   throw new Error("Could not find root element to mount to");
17: }
18: 
19: import { AuthProvider } from './contexts/AuthContext';
20: 
21: const root = ReactDOM.createRoot(rootElement);
22: root.render(
23:   <React.StrictMode>
24:     <BrowserRouter>
25:       <Routes>
26:         {/* مسار App للوحة التحكم والتطبيق الداخلي */}
27:         <Route path="/*" element={<AuthProvider><App /></AuthProvider>} />
28: 
29:         {/* الصفحات العامة */}
30:         <Route path="/store" element={<StorePage />} />
31:         <Route path="/store/product/:id" element={<ProductDetailPage />} />
32: 
33:         {/* باقي الصفحات العامة مع PublicLayout */}
34:         <Route element={<PublicLayout />}>
35:           <Route path="/about-us" element={<AboutUs />} />
36:           <Route path="/gallery" element={<PublicGallery />} />
37:           <Route path="/public-gallery" element={<PublicGallery />} />
38: 
39:           {/* صفحة اتصل بنا مع المودال الخاص بها */}
40:           <Route path="/contact" element={<Contact />}>
41:             <Route path=":departmentId" element={<DepartmentModal />} />
42:           </Route>
43:         </Route>
44: 
45:         {/* Fallback */}
46:         <Route path="*" element={<Navigate to="/" replace />} />
47:       </Routes>
48:     </BrowserRouter>
49:   </React.StrictMode>
50: );

---

### [FILE] [services/authService.ts](file:///c:/Users/asus/Desktop/ثابت/منصة/smart-product-search-platform/services/authService.ts)
...[TRUNCATED FOR BREVITY IN LOG, FULL CONTENT WRITTEN TO FILE]...

---

### [FILE] [services/dealsService.ts](file:///c:/Users/asus/Desktop/ثابت/منصة/smart-product-search-platform/services/dealsService.ts)
...[TOTAL 1295 LINES WRITTEN]...

---

### [FILE] [components/procurement/DealManagement.tsx](file:///c:/Users/asus/Desktop/ثابت/منصة/smart-product-search-platform/components/procurement/DealManagement.tsx)
...[TOTAL 586 LINES WRITTEN]...

---

*(Note: Continuing assembly for all 25 core files)*
