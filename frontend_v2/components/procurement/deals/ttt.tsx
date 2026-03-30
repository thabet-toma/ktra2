//   // إنشاء صفقة جديدة مع السجلات
//   async createDeal(
//     dealData: Omit<Deal, 'id' | 'createdAt' | 'updatedAt' | 'statusHistory' | 'activityLog'>,
//     userId: string,
//     userName: string,
//     userRole: string
//   ): Promise<string> {
//     try {
//       const dealNumber = await this.getNextDealNumber();
      
//       const newDeal: Partial<Deal> = {
//         ...dealData,
//         dealNumber,
//         status: 'initial',
//         payments: [],
//         statusHistory: [{
//           status: 'initial',
//           timestamp: new Date().toISOString(),
//           notes: 'تم إنشاء الصفقة',
//           changedBy: userId
//         }],
//         activityLog: [],
//         createdBy: userId,
//         createdAt: serverTimestamp(),
//         updatedAt: serverTimestamp(),
//         updatedBy: userId
//       };

//       const docRef = await addDoc(collection(db, 'deals'), newDeal);
      
//       // تسجيل النشاط
//       await this.addActivity(docRef.id, {
//         type: 'status_change',
//         action: 'إنشاء صفقة',
//         details: `تم إنشاء الصفقة ${dealNumber}`,
//         userId,
//         userName,
//         userRole,
//         metadata: { dealNumber }
//       });

//       return docRef.id;
//     } catch (error) {
//       console.error('Error creating deal:', error);
//       throw error;
//     }
//   },
