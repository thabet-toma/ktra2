// import { db } from "@/firebaseConfig";
// import { PriceOffer } from "@/types";
// import { collection, query } from "firebase/firestore";
// import { orderBy, onSnapshot, doc, setDoc, updateDoc, deleteDoc, getDoc } from "firebase/firestore";

// // --- Price Offers Service ---
// export const priceOffersService = {
//     subscribeToPriceOffers: (callback: (offers: PriceOffer[]) => void) => {
//         const q = query(collection(db, "price_offers"), orderBy("createdAt", "desc"));
//         return onSnapshot(q, (snapshot) => {
//             const offers = snapshot.docs.map(doc => doc.data() as PriceOffer);
//             callback(offers);
//         });
//     },

//     addPriceOfferToDb: async (offer: PriceOffer) => {
//         const offerRef = doc(db, "price_offers", offer.id);
//         await setDoc(offerRef, removeUndefined(offer));
//     },

//     updatePriceOfferInDb: async (offer: PriceOffer) => {
//         const offerRef = doc(db, "price_offers", offer.id);
//         await updateDoc(offerRef, removeUndefined(offer) as any);
//     },

//     deletePriceOfferFromDb: async (offerId: string) => {
//         const offerRef = doc(db, "price_offers", offerId);
//         await deleteDoc(offerRef);
//     },

//     getPriceOfferById: async (offerId: string): Promise<PriceOffer | null> => {
//         const offerRef = doc(db, "price_offers", offerId);
//         const snap = await getDoc(offerRef);
//         return snap.exists() ? (snap.data() as PriceOffer) : null;
//     }
// };
